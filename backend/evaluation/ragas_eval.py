"""RAGAS evaluation over a hand-written Gujarati test set.

The test set is answered by the real pipeline — the same LangGraph app the API
serves — and the resulting (question, contexts, answer, reference) rows are
scored by RAGAS:

  faithfulness      does the answer stay inside the retrieved passages?
  answer_relevancy  does the answer actually address the question?
  context_recall    did retrieval find the passages the reference needs?

Two things are measured outside RAGAS, because RAGAS has no metric for them:
refusal accuracy (did the system correctly say "not found" on questions whose
answers are not in the book?) and citation-page accuracy.

Free-tier rate limits make the judge the bottleneck, so RAGAS is run with a
single worker and generous timeouts rather than its default parallelism.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import config
from db import database
from qa.graph import answer_question

logger = logging.getLogger(__name__)

TEST_SET_PATH = Path(__file__).parent / "test_set.json"


# ------------------------------------------------------------- test set ----
def load_test_set(doc_id: Optional[str] = None, path: Path = None) -> List[Dict[str, Any]]:
    """Load test cases, optionally keeping only those tagged for one document."""
    path = path or TEST_SET_PATH
    if not path.exists():
        raise FileNotFoundError(f"Test set not found at {path}")

    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)

    cases = payload["cases"] if isinstance(payload, dict) else payload
    if doc_id:
        # Cases with no doc_id are generic and run against whatever book is
        # being evaluated; cases naming a doc_id only run for that book.
        cases = [c for c in cases if c.get("doc_id") in (None, "", doc_id)]
    return cases


# ------------------------------------------------------------ run the app --
def collect_predictions(doc_id: str, cases: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Answer every test question through the live graph."""
    rows: List[Dict[str, Any]] = []
    for i, case in enumerate(cases, start=1):
        question = case["question"]
        logger.info("evaluating %d/%d: %s", i, len(cases), question[:60])
        try:
            result = answer_question(doc_id, question)
        except Exception as exc:
            logger.error("Pipeline failed on %r: %s", question, exc)
            result = {"answer": "", "found": False, "contexts": [], "citations": [],
                      "rewrites_used": 0}
        rows.append({
            "question": question,
            "reference": case.get("ground_truth", "") or "",
            "answer": result.get("answer", ""),
            "contexts": result.get("contexts", []),
            "found": bool(result.get("found")),
            "citations": result.get("citations", []),
            "rewrites_used": result.get("rewrites_used", 0),
            "expected_answerable": bool(case.get("answerable", True)),
            "expected_pages": case.get("expected_pages", []),
        })
    return rows


# --------------------------------------------------- non-RAGAS measures ----
def refusal_metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """How well the system refuses questions the book cannot answer.

    This is the metric that matters most for the project's core claim, and no
    standard RAG metric covers it: RAGAS scores answers, not abstentions.
    """
    negatives = [r for r in rows if not r["expected_answerable"]]
    positives = [r for r in rows if r["expected_answerable"]]

    correct_refusals = sum(1 for r in negatives if not r["found"])
    false_refusals = sum(1 for r in positives if not r["found"])

    return {
        "unanswerable_cases": len(negatives),
        "correct_refusals": correct_refusals,
        # Of the questions not in the book, how many did we correctly decline?
        "refusal_recall": round(correct_refusals / len(negatives), 3) if negatives else None,
        "answerable_cases": len(positives),
        "false_refusals": false_refusals,
        # Of the answerable questions, how many did we wrongly decline?
        "false_refusal_rate": round(false_refusals / len(positives), 3) if positives else None,
    }


def citation_metrics(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Fraction of answers whose citations include an expected page."""
    checked = [r for r in rows if r["expected_pages"] and r["found"]]
    if not checked:
        return {"cases_with_expected_pages": 0, "page_hit_rate": None}

    hits = 0
    for row in checked:
        cited = set()
        for citation in row["citations"]:
            cited.update(range(int(citation["page_start"]), int(citation["page_end"]) + 1))
        if cited & set(int(p) for p in row["expected_pages"]):
            hits += 1
    return {
        "cases_with_expected_pages": len(checked),
        "page_hit_rate": round(hits / len(checked), 3),
    }


# ------------------------------------------------------------ ragas run ----
def _build_judge():
    """Wrap the configured provider as a RAGAS judge LLM plus embeddings."""
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper

    if config.LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq
        judge = ChatGroq(model=config.GROQ_MODEL, api_key=config.GROQ_API_KEY, temperature=0.0)
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        judge = ChatGoogleGenerativeAI(
            model=config.GEMINI_MODEL, google_api_key=config.GEMINI_API_KEY, temperature=0.0
        )

    from langchain_huggingface import HuggingFaceEmbeddings
    # The same embedding model the retriever uses, so answer_relevancy is
    # scored in the space the system actually operates in.
    embeddings = HuggingFaceEmbeddings(
        model_name=config.EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    return LangchainLLMWrapper(judge), LangchainEmbeddingsWrapper(embeddings)


def run_ragas(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Score the answerable cases with RAGAS. Returns {} if RAGAS is unusable."""
    scorable = [r for r in rows if r["expected_answerable"] and r["answer"] and r["contexts"]]
    if not scorable:
        return {"error": "No answerable cases produced an answer with contexts."}

    try:
        from ragas import EvaluationDataset, RunConfig, evaluate
        from ragas.metrics import Faithfulness, LLMContextRecall, ResponseRelevancy
    except ImportError as exc:
        return {"error": f"RAGAS is not installed ({exc}). pip install ragas"}

    dataset = EvaluationDataset.from_list([
        {
            "user_input": r["question"],
            "retrieved_contexts": r["contexts"],
            "response": r["answer"],
            "reference": r["reference"],
        }
        for r in scorable
    ])

    try:
        judge_llm, judge_embeddings = _build_judge()
        metrics = [Faithfulness(), ResponseRelevancy(), LLMContextRecall()]
        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=judge_llm,
            embeddings=judge_embeddings,
            # One worker: the free tier is 15 requests/minute and RAGAS would
            # otherwise fan out and spend the whole quota in seconds.
            run_config=RunConfig(max_workers=1, timeout=180, max_retries=5),
        )
    except Exception as exc:
        logger.exception("RAGAS evaluation failed")
        return {"error": f"RAGAS evaluation failed: {exc}"}

    scores = _extract_scores(result)
    scores["scored_cases"] = len(scorable)
    return scores


def _extract_scores(result: Any) -> Dict[str, Any]:
    """Pull metric name -> score out of a RAGAS result across versions."""
    raw: Dict[str, Any] = {}
    for accessor in (lambda r: r._repr_dict, lambda r: dict(r), lambda r: r.scores):
        try:
            candidate = accessor(result)
            if isinstance(candidate, dict) and candidate:
                raw = candidate
                break
        except Exception:
            continue
    if not raw:
        return {"error": f"Could not read RAGAS scores from {type(result).__name__}",
                "raw": str(result)[:500]}

    out: Dict[str, Any] = {}
    for name, value in raw.items():
        try:
            out[name] = round(float(value), 4)
        except (TypeError, ValueError):
            out[name] = value
    return out


# ---------------------------------------------------------------- driver ---
def evaluate_document(doc_id: str, limit: Optional[int] = None,
                      test_set_path: Path = None) -> Dict[str, Any]:
    """Full evaluation run: answer the test set, score it, persist the result."""
    cases = load_test_set(doc_id, test_set_path)
    if limit:
        cases = cases[:limit]
    if not cases:
        raise ValueError("Test set is empty for this document. Add cases to test_set.json.")

    rows = collect_predictions(doc_id, cases)

    report = {
        "doc_id": doc_id,
        "case_count": len(rows),
        "ragas": run_ragas(rows),
        "refusal": refusal_metrics(rows),
        "citations": citation_metrics(rows),
        "avg_rewrites": round(sum(r["rewrites_used"] for r in rows) / len(rows), 2),
        "per_case": [
            {
                "question": r["question"],
                "found": r["found"],
                "expected_answerable": r["expected_answerable"],
                "answer": r["answer"][:500],
                "cited_pages": sorted({p for c in r["citations"]
                                       for p in range(int(c["page_start"]),
                                                      int(c["page_end"]) + 1)}),
                "rewrites_used": r["rewrites_used"],
            }
            for r in rows
        ],
    }

    try:
        database.save_evaluation(doc_id, report, len(rows))
    except Exception as exc:
        logger.warning("Could not persist evaluation: %s", exc)
    return report


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Run RAGAS evaluation for one document.")
    parser.add_argument("doc_id", help="document id returned by /api/upload")
    parser.add_argument("--limit", type=int, default=None, help="only run the first N cases")
    parser.add_argument("--out", type=Path, default=None, help="write the JSON report here")
    args = parser.parse_args()

    report = evaluate_document(args.doc_id, limit=args.limit)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Report written to {args.out}")
    else:
        print(text)
