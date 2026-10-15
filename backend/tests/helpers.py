"""Shared fixtures: real RetrievedChunk objects and a scripted LLM."""
import json
import os
import re

# Never let a test reach a real provider, whatever backend/.env contains.
os.environ["GEMINI_API_KEY"] = "test-not-a-real-key"
os.environ["GROQ_API_KEY"] = "test-not-a-real-key"
os.environ["SS_LLM_AUTO_FALLBACK"] = "false"

from indexing.hybrid_search import RetrievedChunk  # noqa: E402
from qa.llm_client import BaseLLM  # noqa: E402


def chunk(text, page_start, page_end=None, chunk_id="doc:1", chapter="8. દિગ્દર્શન કલા"):
    return RetrievedChunk(chunk_id=chunk_id, text=text, page_start=page_start,
                          page_end=page_end or page_start, chapter_index=0,
                          chapter_title=chapter, rrf_score=1.0, bm25_rank=1)


# Verbatim from Natya-Sarjan, PDF page 201 (repeated on page 197).
P201 = chunk("નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય અને નટોની ક્રિયા કે કાર્ય "
             "એટલે નટોનો આંગિક અભિનય - આ બંને વચ્ચેે સુમેળ સાધીને દિગ્દર્શક એક "
             "સંયુકત પ્રભાવકારી છબી ઉપસાવે છે.", 201, 202, "doc:370")
# Verbatim from PDF page 15.
P15 = chunk("‘અંધાયુગ’ની રજૂઆત જાપાનીઝ ક્લાસિકલ નાટ્યશૈલી ‘નોહ’ અને ‘કાબૂકી’માં "
            "કરવામાં આવી, ઈબસનના ‘When the Dead Awaken’ની ભજવણી ‘મણિપુરી’ શૈલીમાં થઈ. "
            "છેલ્લાં 50 વર્ષમાં", 14, 15, "doc:16", "1. નાટક – એક અનોખી કળા")
# Verbatim from PDF page 56 (the PDF hyphenates across a line break).
P56 = chunk("યાદ રહે છે માત્ર નાટક વિશેની એકદંર છબી કે પ્રભાવ જેને નાટકની "
            "‘command- ing image’ કહી શકાય.", 55, 56, "doc:100", "1. નાટક – એક અનોખી કળા")
UNRELATED = chunk("નદીના કિનારે ગામ વસેલું હતું.", 40, 40, "doc:9")

# Page text for the fixtures, standing in for the PDF (qa.pages). Each
# two-page fixture's text sits on one page; the other page holds other text.
PAGE_TEXT = {
    ("doc", 201): P201.text,
    ("doc", 202): "નાટકનો એકંદર મૂડ કે વાતાવરણ કેવાં છે તેના આધારે દિગ્દર્શક ડિઝાઇનરો સાથે કામ કરે છે.",
    ("doc", 14): "‘હેમલેટ’ જેવું નાટક 20મી સદીના આધુનિક પોશાક અને વાતાવરણમાં રજૂ કરવામાં આવયું.",
    ("doc", 15): P15.text,
    ("doc", 55): "દિગ્દર્શકે નાટકનો ઊંડો અભ્યાસ કરવો જોઈએ.",
    ("doc", 56): P56.text,
    ("doc", 40): UNRELATED.text,
}


def set_page(doc_id, page, text):
    PAGE_TEXT[(doc_id, page)] = text


from qa import pages as _pages  # noqa: E402

_pages.page_text_source = lambda doc_id, page: PAGE_TEXT.get((doc_id, page))


class ScriptedLLM(BaseLLM):
    """Grades by a predicate, rewrites by a function, verifies claims by a
    predicate, answers from a queue."""
    name = "scripted"

    def __init__(self, relevant=lambda text: True, rewrite=lambda prompt: "rewritten query",
                 answers=("answer",), supported=lambda claim: True):
        self.relevant, self.rewrite, self.answers = relevant, rewrite, list(answers)
        self.supported = supported
        self.prompts = []

    def _complete(self, prompt, system, temperature):
        self.prompts.append(prompt)
        if '"claims"' in prompt:
            claims = re.findall(r"^Claim (\d+) \(cites [^)]*\): (.*)$", prompt, re.MULTILINE)
            return json.dumps({"claims": [
                {"claim": int(n), "supported": bool(self.supported(text)), "reason": "scripted"}
                for n, text in claims]})
        if '"grades"' in prompt:
            passages = prompt.split("Passages:", 1)[1].split("\n\n---\n\n")
            return json.dumps({"grades": [
                {"passage": i, "relevant": self.relevant(p), "reason": "scripted"}
                for i, p in enumerate(passages, start=1)]})
        if prompt.startswith("Original question"):
            return self.rewrite(prompt)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
