"""Prompt construction for the QA graph.

The grounding rules live here, not in the graph, so the exact wording that
keeps the model inside the book is reviewable in one place. Three prompts are
built: answer, relevance grading, and query rewriting.
"""
from __future__ import annotations

import re
from typing import List, Sequence

import config

_GUJARATI = re.compile(r"[઀-૿]")


def detect_language(text: str) -> str:
    """'gujarati' if the text contains Gujarati script, else 'english'.

    Script presence is the right test here: a Gujarati question is written in
    Gujarati script, and users routinely mix in English proper nouns.
    """
    return "gujarati" if _GUJARATI.search(text or "") else "english"


# ------------------------------------------------------------ answering ----
ANSWER_SYSTEM = """You are Sahitya Setu, a careful reading assistant for Gujarati literature.

You answer ONLY from the book passages given to you in each request. You are not a general
knowledge assistant and you must not use anything you know outside those passages.

Absolute rules:
1. Every factual statement in your answer must be supported by the supplied passages.
2. Never invent names, events, dates, numbers or quotations that are not in the passages.
3. If the passages do not contain the answer, say so plainly instead of guessing.
4. Cite the page number (and chapter, when given) for each fact you state.
5. Answer in the same language the question was asked in."""


def _format_passages(chunks: Sequence) -> str:
    blocks: List[str] = []
    for i, chunk in enumerate(chunks, start=1):
        pages = (f"page {chunk.page_start}" if chunk.page_start == chunk.page_end
                 else f"pages {chunk.page_start}-{chunk.page_end}")
        header = f"[{i}] {pages}"
        if chunk.chapter_title:
            header += f" | chapter: {chunk.chapter_title}"
        blocks.append(f"{header}\n{chunk.text}")
    return "\n\n---\n\n".join(blocks)


def build_answer_prompt(question: str, chunks: Sequence, language: str = None) -> str:
    """Prompt the model to answer strictly from the retrieved passages."""
    language = language or detect_language(question)

    if language == "gujarati":
        instructions = (
            "સૂચનાઓ:\n"
            "- ફક્ત ઉપર આપેલા ફકરાઓના આધારે જ ઉત્તર આપો.\n"
            "- ઉત્તર ગુજરાતીમાં આપો.\n"
            "- દરેક મુદ્દા પછી કૌંસમાં પાનાનો નંબર લખો, જેમ કે (પાનું ૪૨).\n"
            "- જો ફકરાઓમાં ઉત્તર ન હોય, તો ફક્ત આટલું જ લખો: NOT_FOUND\n"
            "- અનુમાન કે બહારની માહિતી ઉમેરશો નહીં."
        )
    else:
        instructions = (
            "Instructions:\n"
            "- Answer using only the passages above.\n"
            "- Answer in English.\n"
            "- After each point, cite the page in parentheses, e.g. (page 42).\n"
            "- If the passages do not contain the answer, reply with exactly: NOT_FOUND\n"
            "- Do not speculate or add outside information."
        )

    return (
        f"Book passages:\n\n{_format_passages(chunks)}\n\n"
        f"===\n\nQuestion: {question}\n\n{instructions}\n\nAnswer:"
    )


# ------------------------------------------------------------- grading -----
GRADE_SYSTEM = (
    "You judge whether retrieved book passages are relevant to a question. "
    "You reply with JSON only — no prose, no code fences."
)


def build_grade_prompt(question: str, chunks: Sequence) -> str:
    """Grade all retrieved passages in one call.

    One batched call instead of one per passage matters on a 15 requests/min
    free tier: grading five chunks separately would spend a third of the
    minute's budget on a single question.
    """
    listing: List[str] = []
    for i, chunk in enumerate(chunks, start=1):
        # Grading needs the gist, not the whole passage.
        snippet = chunk.text[:900]
        listing.append(f"[{i}]\n{snippet}")

    return (
        f"Question: {question}\n\n"
        f"Passages:\n\n" + "\n\n---\n\n".join(listing) + "\n\n"
        "For each passage, decide whether it contains information that helps answer the "
        "question. Be strict: a passage that merely mentions the same topic, character or "
        "place without addressing the question is NOT relevant.\n\n"
        "Reply with JSON of exactly this shape:\n"
        '{"grades": [{"passage": 1, "relevant": true, "reason": "short reason"}]}\n'
        "Include one entry per passage, in order."
    )


# ------------------------------------------------------------ rewriting ----
REWRITE_SYSTEM = (
    "You rewrite search queries for a Gujarati book retrieval system. "
    "You reply with the rewritten query only — no explanation."
)


def build_rewrite_prompt(question: str, attempt: int, previous: Sequence[str] = ()) -> str:
    """Ask for a differently-phrased query after retrieval came back irrelevant."""
    tried = ""
    if previous:
        tried = "Queries already tried (do not repeat them):\n" + \
                "\n".join(f"- {q}" for q in previous) + "\n\n"

    strategy = (
        "Use different, more literal words that would physically appear in the book's text."
        if attempt == 1 else
        "Broaden the query: keep only the core subject as keywords and drop the question framing."
    )

    return (
        f"Original question: {question}\n\n{tried}"
        "The search returned nothing relevant. Rewrite the query so a keyword + semantic "
        f"search over a Gujarati book is more likely to find the right passage.\n\n"
        f"Strategy for this attempt: {strategy}\n\n"
        "Keep the query in the same script as the original question. Include likely proper "
        "nouns and domain terms. Output only the rewritten query."
    )


# ------------------------------------------------------------- fallback ----
def not_found_answer(language: str) -> str:
    if language == "gujarati":
        return "આ પ્રશ્નનો ઉત્તર આપેલા પુસ્તકમાં મળ્યો નથી."
    return "This question could not be answered from the uploaded book."
