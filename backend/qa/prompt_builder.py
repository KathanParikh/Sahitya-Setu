"""Prompt construction for the QA graph.

The grounding rules live here, not in the graph, so the exact wording that
keeps the model inside the book is reviewable in one place. Three prompts are
built: answer, relevance grading, and query rewriting.
"""
from __future__ import annotations

import re
from typing import List, Sequence

import config
from qa import pages

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
5. Answer in the same language the question was asked in.
6. Do not elaborate. Add no synonyms, examples, descriptive words or explanations
   that the passages do not state, even if they are true and seem helpful. When
   defining a term, quote the complete sentence or clause in which the passage
   defines it, both sides included (for "X એટલે Y", quote all of it), never a
   fragment. Never define a term with itself.
7. Anything inside quotation marks must be copied character for character from a
   passage, spelling included. If you are not copying exactly, do not use quotation
   marks. Never write a number, year or English word the passages do not contain."""


def _marked(chunk) -> str:
    """Passage text with ⟪પાનું N⟫ where page N begins (see qa.pages)."""
    try:
        return pages.with_page_markers(chunk)
    except Exception:
        return chunk.text


def _format_passages(chunks: Sequence) -> str:
    blocks: List[str] = []
    for i, chunk in enumerate(chunks, start=1):
        pages = (f"page {chunk.page_start}" if chunk.page_start == chunk.page_end
                 else f"pages {chunk.page_start}-{chunk.page_end}")
        header = f"[{i}] {pages}"
        if chunk.chapter_title:
            header += f" | chapter: {chunk.chapter_title}"
        blocks.append(f"{header}\n{_marked(chunk)}")
    return "\n\n---\n\n".join(blocks)


def build_answer_prompt(question: str, chunks: Sequence, language: str = None,
                        book_title: str = None) -> str:
    """Prompt the model to answer strictly from the retrieved passages."""
    language = language or detect_language(question)
    book = f'Book: "{book_title}"\n\n' if book_title else ""

    if language == "gujarati":
        instructions = (
            "સૂચનાઓ:\n"
            "- ફક્ત ઉપર આપેલા ફકરાઓના આધારે જ ઉત્તર આપો.\n"
            "- ઉત્તર ગુજરાતીમાં આપો.\n"
            "- દરેક મુદ્દા પછી કૌંસમાં જે પાના પર એ લખાણ છે તે ચોક્કસ પાનું લખો, જેમ કે (પાનું ૪૨). "
            "ફકરામાં ⟪પાનું N⟫ નિશાની પછીનું લખાણ પાના N પર છે, નિશાની પહેલાંનું લખાણ તેની "
            "આગળના પાના પર. વાક્ય બે પાનાંમાં ફેલાયેલું હોય તો જ (પાનાં ૪૨-૪૩) લખો. "
            "નિશાની ઉત્તરમાં ન લખો.\n"
            "- જો ફકરાઓમાં ઉત્તર ન હોય, તો ફક્ત આટલું જ લખો: NOT_FOUND\n"
            "- અનુમાન કે બહારની માહિતી ઉમેરશો નહીં.\n"
            "- ફકરામાં ન લખ્યા હોય એવા સમાનાર્થી શબ્દો, ઉદાહરણો કે વિસ્તાર ઉમેરશો નહીં, "
            "ભલે તે સાચા લાગે.\n"
            "- કોઈ શબ્દની વ્યાખ્યા આપતી વખતે ફકરામાં જે આખા વાક્ય કે વાક્યખંડમાં તેની વ્યાખ્યા "
            "આપી છે તે બંને બાજુ સહિત (જેમ કે \"X એટલે Y\" આખું) અવતરણ ચિહ્નોમાં ટાંકો; "
            "ટુકડો નહીં. શબ્દની વ્યાખ્યા એ જ શબ્દથી ન આપો.\n"
            "- અવતરણ ચિહ્નોમાંનું લખાણ ફકરામાંથી અક્ષરશઃ, જોડણી સહિત, નકલ કરેલું હોવું જોઈએ; "
            "નહીં તો અવતરણ ચિહ્નો ન વાપરો."
        )
    else:
        instructions = (
            "Instructions:\n"
            "- Answer using only the passages above.\n"
            "- Answer in English.\n"
            "- After each point, cite the exact page the text is on, e.g. (page 42). In a "
            "passage, text after a ⟪પાનું N⟫ mark is on page N and text before it is on the "
            "page before. Cite (pages 42-43) only for a sentence that runs across both. Do not "
            "copy the marks into the answer.\n"
            "- If the passages do not contain the answer, reply with exactly: NOT_FOUND\n"
            "- Do not speculate or add outside information.\n"
            "- Add no synonyms, examples or elaboration the passages do not state, "
            "even if they seem true.\n"
            "- When defining a term, quote the complete sentence or clause that defines it, "
            "both sides included (all of \"X means Y\"), never a fragment. Never define a "
            "term with itself.\n"
            "- Text inside quotation marks must be copied exactly from a passage, spelling "
            "included; otherwise do not use quotation marks."
        )

    return (
        f"{book}Book passages:\n\n{_format_passages(chunks)}\n\n"
        f"===\n\nQuestion: {question}\n\n{instructions}\n\nAnswer:"
    )


def build_regrounding_prompt(answer_prompt: str, previous_answer: str,
                             problems: Sequence[str]) -> str:
    """Second attempt after the grounding check rejected the first answer."""
    listed = "\n".join(f"- {p}" for p in problems)
    return (
        f"{answer_prompt} {previous_answer}\n\n"
        "===\n\nThat answer failed verification against the passages:\n"
        f"{listed}\n\n"
        "Write the answer again. Copy any quoted text exactly, character for character, "
        "from a passage, or remove the quotation marks. Cite the exact page each "
        "statement is on (text after a ⟪પાનું N⟫ mark is on page N), only pages shown in "
        "the passage headers. Use no number, year or English word that the passages do not "
        "contain. Every statement must be supported by the passage it cites: add no name, "
        "detail or explanation, and reword only where the meaning stays identical; "
        "prefer the passage's own words. If the passages do not support an answer, "
        "reply with exactly: NOT_FOUND"
        "\n\nAnswer:"
    )


# ------------------------------------------------------- claim checking ----
CLAIM_CHECK_SYSTEM = (
    "You verify that statements are fully supported by book passages. You judge only "
    "against the passages given, never your own knowledge. You reply with JSON only."
)


def build_claim_check_prompt(claims: Sequence) -> str:
    """Ask for a supported/unsupported verdict on each claim against its cited passages.

    `claims` are qa.grounding.Claim objects. Each passage is printed once and
    claims refer to it by number, so a long answer does not repeat passages.
    """
    passage_ids: dict = {}
    blocks: List[str] = []
    for claim in claims:
        for c in claim.passages:
            if c.chunk_id not in passage_ids:
                passage_ids[c.chunk_id] = len(passage_ids) + 1
                pages = (f"page {c.page_start}" if c.page_start == c.page_end
                         else f"pages {c.page_start}-{c.page_end}")
                blocks.append(f"[P{passage_ids[c.chunk_id]}] {pages}\n{c.text}")
    listing = []
    for i, claim in enumerate(claims, start=1):
        refs = ", ".join(f"P{passage_ids[c.chunk_id]}" for c in claim.passages)
        novel = ", ".join(claim.novel) if claim.novel else "none"
        listing.append(f"Claim {i} (cites {refs}): {claim.text}\n"
                       f"  Words in this claim not found in its passages: {novel}")
    return (
        "Passages:\n\n" + "\n\n---\n\n".join(blocks) + "\n\n===\n\n"
        "Claims:\n\n" + "\n\n".join(listing) + "\n\n===\n\n"
        "For each claim, decide whether it is fully supported by the passages it cites.\n"
        "- SUPPORTED only if every piece of information in the claim is stated in, or "
        "directly follows from, those passages. Rewording and reordering are fine.\n"
        "- UNSUPPORTED if it adds anything those passages do not state: a name, title, "
        "date, number, example, cause, purpose, quality, comparison or explanation.\n"
        "- UNSUPPORTED if it changes the meaning: swaps who or what, negates, "
        "generalises, narrows, or attributes something to the wrong person or thing.\n"
        "- For each listed word not found in the passages, decide whether it only "
        "rephrases the passages' wording. If it adds information, the claim is "
        "UNSUPPORTED.\n"
        "- If you are unsure, the claim is UNSUPPORTED.\n\n"
        "Reply with JSON of exactly this shape, one entry per claim, in order:\n"
        '{"claims": [{"claim": 1, "supported": false, "reason": "short reason"}]}'
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
        # The whole passage: the grader decides whether it states the answer,
        # and in Gujarati a chunk often runs past 1,000 characters, so a cut
        # hid the answer at the end of most passages.
        listing.append(f"[{i}]\n{chunk.text}")

    return (
        f"Question: {question}\n\n"
        f"Passages:\n\n" + "\n\n---\n\n".join(listing) + "\n\n"
        "For each passage, decide whether it actually states the answer to the question. "
        "Be strict:\n"
        "- Relevant only if the question could be answered from this passage alone.\n"
        "- Every qualifier in the question must be satisfied by what the passage says "
        "(e.g. who, when, before/after, unseen, first). A passage about something similar "
        "that lacks one of them is NOT relevant.\n"
        "- Sharing words, the topic, a character or a place is NOT enough.\n\n"
        "Reply with JSON of exactly this shape:\n"
        '{"grades": [{"passage": 1, "relevant": true, "reason": "short reason"}]}\n'
        "Include one entry per passage, in order."
    )


build_grading_prompt = build_grade_prompt  # name used in the project brief


# ------------------------------------------------------------ rewriting ----
REWRITE_SYSTEM = (
    "You rewrite search queries for a Gujarati book retrieval system. "
    "You reply with the rewritten query only — no explanation. "
    "You never add facts, names or dates from your own knowledge."
)


def build_rewrite_prompt(question: str, attempt: int = 1, previous: Sequence[str] = ()) -> str:
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
        "Keep the query in the same script as the original question. You may add synonyms "
        "and domain vocabulary for the subject the question already names. Do not add "
        "names, dates, numbers or facts that are not in the original question: you have not "
        "seen the book, and a guessed answer in the query biases the search toward it. "
        "Output only the rewritten query."
    )


# ------------------------------------------------------------- fallback ----
def not_found_answer(language: str) -> str:
    if language == "gujarati":
        return "આ પ્રશ્નનો ઉત્તર આપેલા પુસ્તકમાં મળ્યો નથી."
    return "This question could not be answered from the uploaded book."
