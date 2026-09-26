"""The agentic QA pipeline, built as a LangGraph state machine.

A fixed retrieve-then-answer pipeline always answers, even when retrieval
returned nothing useful — which is exactly when a grounded system should
refuse. This graph inserts a grading step between retrieval and generation,
and gives the system two chances to rewrite its own query before giving up:

        retrieve ──► grade ──┬─(relevant)──────► generate ──┬─► END
            ▲                │                              │
            │                ├─(poor, retries left)─► rewrite
            └────────────────┘                              │
                             └─(poor, out of retries)─► fallback ─► END
                                                             ▲
                            (generate says NOT_FOUND) ────────┘

The fallback node is the only thing that produces a "not found" answer, so
there is exactly one place in the system where refusal is decided.
"""
from __future__ import annotations

import logging
import operator
import time
from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict

import config
from indexing.hybrid_search import RetrievedChunk, hybrid_search
from qa import prompt_builder
from qa.llm_client import BaseLLM, LLMError, get_llm

logger = logging.getLogger(__name__)


# ------------------------------------------------------------- state -------
class QAState(TypedDict, total=False):
    doc_id: str
    original_question: str
    question: str               # the current (possibly rewritten) query
    language: str               # "gujarati" | "english"
    documents: List[RetrievedChunk]
    relevant: List[RetrievedChunk]
    attempts: int               # rewrites used so far
    tried_queries: List[str]
    answer: str
    found: bool
    llm_error: str             # set when a provider call failed outright
    citations: List[Dict[str, Any]]
    trace: Annotated[List[Dict[str, Any]], operator.add]


def _note(node: str, **fields) -> Dict[str, Any]:
    """One trace entry — surfaced in the API response so the graph's decisions
    are visible during a demo instead of being a black box."""
    return {"node": node, "t": round(time.time(), 3), **fields}


# ------------------------------------------------------------- nodes -------
def retrieve_node(state: QAState) -> Dict[str, Any]:
    """Hybrid search: BM25 + vector, fused with RRF."""
    query = state["question"]
    chunks = hybrid_search(state["doc_id"], query, top_k=config.FINAL_TOP_K)
    logger.info("retrieve: %d chunks for %r", len(chunks), query)
    return {
        "documents": chunks,
        "tried_queries": list(state.get("tried_queries", [])) + [query],
        "trace": [_note("retrieve", query=query, retrieved=len(chunks),
                        chunk_ids=[c.chunk_id for c in chunks])],
    }


def grade_node(state: QAState, llm: Optional[BaseLLM] = None) -> Dict[str, Any]:
    """Ask the LLM which retrieved passages actually answer the question.

    A grading failure must not silently drop to "not found": if the grader
    cannot be reached, every retrieved passage is passed through and the
    answer prompt's own grounding rules take over.
    """
    documents = state.get("documents") or []
    if not documents:
        return {"relevant": [], "trace": [_note("grade", graded=0, relevant=0,
                                                reason="nothing retrieved")]}

    prompt = prompt_builder.build_grade_prompt(state["question"], documents)
    try:
        llm = llm or get_llm()
        payload = llm.generate_json(prompt, system=prompt_builder.GRADE_SYSTEM, temperature=0.0)
        grades = payload.get("grades", []) if isinstance(payload, dict) else payload
        keep: List[RetrievedChunk] = []
        reasons: List[str] = []
        for grade in grades or []:
            if not isinstance(grade, dict):
                continue
            position = int(grade.get("passage", 0))
            if 1 <= position <= len(documents) and bool(grade.get("relevant")):
                keep.append(documents[position - 1])
                reasons.append(str(grade.get("reason", ""))[:120])
        return {
            "relevant": keep,
            "trace": [_note("grade", graded=len(documents), relevant=len(keep),
                            reasons=reasons)],
        }
    except (LLMError, ValueError, TypeError, AttributeError) as exc:
        logger.warning("Grading failed (%s); passing all retrieved chunks through.", exc)
        return {
            "relevant": list(documents),
            "trace": [_note("grade", graded=len(documents), relevant=len(documents),
                            error=str(exc)[:200], fallback="grader unavailable")],
        }


def rewrite_node(state: QAState, llm: Optional[BaseLLM] = None) -> Dict[str, Any]:
    """Rephrase the query after retrieval came back irrelevant."""
    attempts = state.get("attempts", 0) + 1
    original = state["original_question"]
    tried = state.get("tried_queries", [])

    try:
        llm = llm or get_llm()
        rewritten = llm.generate(
            prompt_builder.build_rewrite_prompt(original, attempts, tried),
            system=prompt_builder.REWRITE_SYSTEM,
            temperature=0.3,
        ).strip().strip('"')
    except LLMError as exc:
        # Without the LLM, strip the question framing down to its keywords —
        # a crude rewrite is still a different query than the one that failed.
        rewritten = _keyword_only(original)
        logger.warning("Rewrite via LLM failed (%s); using keyword reduction.", exc)

    if not rewritten or rewritten in tried:
        rewritten = _keyword_only(original)

    logger.info("rewrite %d: %r -> %r", attempts, state["question"], rewritten)
    return {
        "question": rewritten,
        "attempts": attempts,
        "trace": [_note("rewrite", attempt=attempts, new_query=rewritten)],
    }


_QUESTION_WORDS = {
    "શું", "કેમ", "કોણ", "ક્યાં", "ક્યારે", "કેવી", "કેટલા", "કેટલી", "શા",
    "what", "why", "who", "where", "when", "how", "which", "is", "are", "the",
    "of", "in", "a", "an", "does", "did", "do", "tell", "me", "about",
}


def _keyword_only(question: str) -> str:
    """Drop interrogatives, keep the content words."""
    words = [w for w in question.split() if w.strip("?।,.").lower() not in _QUESTION_WORDS]
    return " ".join(words).strip("?। ") or question


def generate_node(state: QAState, llm: Optional[BaseLLM] = None) -> Dict[str, Any]:
    """Answer from the graded-relevant passages, with citations."""
    chunks = state.get("relevant") or []
    language = state.get("language") or prompt_builder.detect_language(state["original_question"])

    prompt = prompt_builder.build_answer_prompt(state["original_question"], chunks, language)
    try:
        llm = llm or get_llm()
        answer = llm.generate(prompt, system=prompt_builder.ANSWER_SYSTEM)
    except LLMError as exc:
        # A provider outage is not the same as "the book does not say". Record
        # it so the caller can report a service error instead of a refusal the
        # system has not actually earned.
        logger.error("Generation failed: %s", exc)
        return {
            "answer": "", "found": False, "llm_error": str(exc)[:300],
            "trace": [_note("generate", error=str(exc)[:200])],
        }

    # The model is instructed to emit this token when the passages fall short,
    # which is a second line of defence behind the grader.
    if "NOT_FOUND" in answer.upper():
        return {
            "answer": "", "found": False,
            "trace": [_note("generate", outcome="model reported NOT_FOUND")],
        }

    return {
        "answer": answer,
        "found": True,
        "citations": [_citation(c) for c in chunks],
        "trace": [_note("generate", outcome="answered", passages=len(chunks),
                        answer_chars=len(answer))],
    }


def fallback_node(state: QAState) -> Dict[str, Any]:
    """The single place a refusal is produced."""
    language = state.get("language") or prompt_builder.detect_language(state["original_question"])
    return {
        "answer": prompt_builder.not_found_answer(language),
        "found": False,
        "citations": [],
        "trace": [_note("fallback", attempts=state.get("attempts", 0),
                        tried_queries=state.get("tried_queries", []))],
    }


def _citation(chunk: RetrievedChunk) -> Dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "chapter_index": chunk.chapter_index,
        "chapter_title": chunk.chapter_title,
        "label": chunk.citation(),
        "snippet": chunk.text[:300],
        "retrieved_by": chunk.sources,
    }


# --------------------------------------------------------- conditionals ----
def decide_after_grade(state: QAState) -> str:
    relevant = state.get("relevant") or []
    if len(relevant) >= config.MIN_RELEVANT_CHUNKS:
        return "generate"
    if state.get("attempts", 0) < config.MAX_QUERY_REWRITES:
        return "rewrite"
    return "fallback"


def decide_after_generate(state: QAState) -> str:
    return "done" if state.get("found") else "fallback"


# ------------------------------------------------------------- graph -------
_compiled = None


def build_graph(llm: Optional[BaseLLM] = None):
    """Wire the nodes into a compiled LangGraph app.

    `llm` is injectable so evaluation and tests can drive the graph with a
    stub instead of burning free-tier quota.
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(QAState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("grade", lambda s: grade_node(s, llm))
    graph.add_node("rewrite", lambda s: rewrite_node(s, llm))
    graph.add_node("generate", lambda s: generate_node(s, llm))
    graph.add_node("fallback", fallback_node)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges(
        "grade", decide_after_grade,
        {"generate": "generate", "rewrite": "rewrite", "fallback": "fallback"},
    )
    graph.add_edge("rewrite", "retrieve")
    graph.add_conditional_edges(
        "generate", decide_after_generate,
        {"done": END, "fallback": "fallback"},
    )
    graph.add_edge("fallback", END)
    return graph.compile()


def get_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def reset_graph() -> None:
    global _compiled
    _compiled = None


# ------------------------------------------------------------- entry -------
def answer_question(doc_id: str, question: str, app=None) -> Dict[str, Any]:
    """Run one question through the graph and return an API-shaped result."""
    app = app or get_graph()
    started = time.time()

    initial: QAState = {
        "doc_id": doc_id,
        "original_question": question,
        "question": question,
        "language": prompt_builder.detect_language(question),
        "documents": [],
        "relevant": [],
        "attempts": 0,
        "tried_queries": [],
        "found": False,
        "trace": [],
    }
    # Each rewrite costs a full retrieve+grade lap; the limit keeps a runaway
    # graph from looping past LangGraph's default recursion ceiling.
    final = app.invoke(initial, {"recursion_limit": 6 + config.MAX_QUERY_REWRITES * 4})

    return {
        "doc_id": doc_id,
        "question": question,
        "answer": final.get("answer", ""),
        "found": bool(final.get("found")),
        "llm_error": final.get("llm_error", ""),
        "citations": final.get("citations", []),
        "language": final.get("language", "english"),
        "rewrites_used": final.get("attempts", 0),
        "queries_tried": final.get("tried_queries", []),
        "contexts": [c.text for c in (final.get("relevant") or [])],
        "retrieved": [c.to_dict() for c in (final.get("documents") or [])],
        "trace": final.get("trace", []),
        "elapsed_seconds": round(time.time() - started, 2),
    }
