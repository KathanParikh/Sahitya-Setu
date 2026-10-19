"""Regressions from the 2026-10-15 live verification run.

F1, F2, F3, F5 and F6 failed there only because the probe answers cited the
whole chunk range while each sentence sits on one page. The fixtures below
reproduce the real page split from the PDF (excerpts of the book's text),
so these tests pin both halves of the rule: the exact page is accepted and
reaches the meaning check; the range, or another page, is rejected for the
page alone.
"""
import unittest

from tests.helpers import P15, P201, ScriptedLLM, chunk, set_page
from qa import grounding

# PDF pages 190-191 (chunk 350): the sentence about Strasberg is on 191.
P190_TEXT = "ફરી સાંભળો, પ્રશ્ન એ નથી કે નટ જાતે ‘feel’ કરે છે કે નહીં, ખરો પ્રશ્ન એ છે કે પ્રેક્ષકો ‘feel’ કરે છે કે નહીં."
P191_TEXT = ("અમેરિકન નાટ્યગુરુ લી સટ્રેસબર્ગ(જે સ્ટાનિસલાવ્સ્કીકીથી જ પ્રભાવિત થયેલો) કહેતો કે નટ જેનો "
             "પાઠ ભજવવાનો છે તે પણ એક માણસ જ છે જે તેની જેમ જ જીવે છે. સટ્રેસબર્ગ માટે નાટક શરૂ "
             "થાય કે તરત નટ પાત્રનાં જીવનમાં પ્રવેશ કરે એટલું પર્યાપ્ત નહોતું.")
C350 = chunk(f"{P190_TEXT} {P191_TEXT}", 190, 191, "real:350", "7. અભિનય કલા")

# PDF pages 151-152 (chunk 279): the fourth-wall sentences are on 152.
P151_TEXT = "નાટ્યશૈલીઓના મુખ્યત્વે બે પ્રકાર છે: વાસતવવાદી શૈલી અને બિનવાસ્તવિક શૈલી."
P152_TEXT = ("કલ્પિત ધારણા એવી છે કે રંગમંચને ઢાંકતો મુખય પડદો(main curtain) એ નાટકના ઘરની ચોથી "
             "દીવાલ છે. નાટક શરૂ થતાં જ એ પડદો એટલે કે પેલી કલ્પિત ચોથી દીવાલ ખસી જાય છે અને "
             "પરિણામે સામે બેઠેલ પ્રેક્ષકો દીવાનખંડમાં ભજવાતાં નાટકરૂપી જીવનને પ્રત્યક્ષ જોઈ શકે છે.")
C279 = chunk(f"{P151_TEXT} {P152_TEXT}", 151, 152, "real:279", "6. નાટકની શૈલીઓ")

for page, text in ((190, P190_TEXT), (191, P191_TEXT), (151, P151_TEXT), (152, P152_TEXT)):
    set_page("real", page, text)

# (case, paraphrase, passage, exact page(s), the chunk's other page)
FAILED_CASES = [
    ("F1", "વાચિક અભિનય એટલે નાટકના સંવાદો, અને આંગિક અભિનય એટલે નટોની ક્રિયા કે કાર્ય", P201, "201", "202"),
    ("F2", "‘અંધાયુગ’ જાપાનની ‘નોહ’ અને ‘કાબૂકી’ શૈલીમાં રજૂ થયું હતું", P15, "15", "14"),
    ("F3", "સટ્રેસબર્ગ માટે નાટક શરૂ થતાં જ નટ પાત્રના જીવનમાં પ્રવેશે એટલું પૂરતું નહોતું", C350, "191", "190"),
    ("F5", "નાટક શરૂ થાય ત્યારે મુખ્ય પડદો, એટલે કે કલ્પિત ચોથી દીવાલ, ખસી જાય છે", C279, "152", "151"),
    ("F6", "લી સટ્રેસબર્ગ સ્ટાનિસલાવ્સ્કીથી પ્રભાવિત હતા", C350, "191", "190"),
]


def page_only(problems):
    return problems and all(("cites page" in p or "cannot establish which" in p) for p in problems)


class FailedParaphrases(unittest.TestCase):
    def test_exact_page_passes_and_reaches_the_meaning_check(self):
        for case, text, passage, exact, _ in FAILED_CASES:
            r = grounding.check_answer(f"{text} (પાનું {exact})", [passage])
            self.assertTrue(r.ok, (case, r.problems))
            claims = grounding.extract_claims(r.answer, [passage])
            self.assertFalse(claims[0].verbatim, case)  # a paraphrase: the verifier decides
            llm = ScriptedLLM(supported=lambda c: True)
            problems, checked = grounding.verify_claims(r.answer, [passage], llm)
            self.assertEqual((problems, checked), ([], 1), case)

    def test_whole_chunk_range_is_rejected_for_the_page_only(self):
        for case, text, passage, exact, other in FAILED_CASES:
            lo, hi = sorted((int(exact), int(other)))
            r = grounding.check_answer(f"{text} (પાનાં {lo}-{hi})", [passage])
            self.assertTrue(page_only(r.problems), (case, r.problems))
            self.assertIn(f"is on page(s) [{exact}]", " ".join(r.problems), case)

    def test_the_other_page_of_the_chunk_is_rejected(self):
        for case, text, passage, exact, other in FAILED_CASES:
            r = grounding.check_answer(f"{text} (પાનું {other})", [passage])
            self.assertTrue(page_only(r.problems), (case, r.problems))

    def test_unsupported_answers_at_the_exact_page_still_reach_the_verifier(self):
        # The live U3-U8 probes cited ranges, so only the page check ran; at
        # the exact page they must get past it and be judged on meaning.
        for text, passage, page in (
            ("‘અંધાયુગ’ની રજૂઆત ઇબ્રાહિમ અલ્કાઝીએ જાપાનીઝ ‘નોહ’ અને ‘કાબૂકી’ શૈલીમાં કરી", P15, "15"),
            ("નાટકના સંવાદો એટલે નટોનો આંગિક અભિનય અને નટોની ક્રિયા એટલે નટોનો વાચિક અભિનય", P201, "201"),
            ("લી સટ્રેસબર્ગ સ્ટાનિસલાવ્સ્કીના શિષ્ય હતા", C350, "191"),
            ("નાટક પૂરું થતાં કલ્પિત ચોથી દીવાલ ખસી જાય છે", C279, "152"),
            ("‘અંધાયુગ’ હંમેશાં ‘નોહ’ શૈલીમાં જ ભજવાય છે", P15, "15"),
        ):
            answer = f"{text} (પાનું {page})"
            self.assertTrue(grounding.check_answer(answer, [passage]).ok, text)
            problems, checked = grounding.verify_claims(answer, [passage], ScriptedLLM(supported=lambda c: False))
            self.assertEqual(checked, 1, text)
            self.assertIn("claim not supported", problems[0], text)

    def test_invented_words_are_rejected_for_content_even_at_the_exact_page(self):
        r = grounding.check_answer("કાબૂકીની શરૂઆત ઓકુની નામની નર્તકીએ કરી હતી (પાનું 15)", [P15])
        self.assertIn("claim adds words", " ".join(r.problems))


class CitationCorrection(unittest.TestCase):
    """2026-10-16 live run on the Std 8 textbook: right answers were refused
    because the model cited the neighbouring page of a two-page passage. The
    graph now moves such a citation to the page that states the claim."""

    def test_range_or_other_page_is_moved_to_the_exact_page(self):
        for case, text, passage, exact, other in FAILED_CASES:
            lo, hi = sorted((int(exact), int(other)))
            for cited in (f"પાનાં {lo}-{hi}", f"પાનું {other}"):
                answer, moved = grounding.snap_citations(f"{text} ({cited})", [passage])
                self.assertEqual(moved, [(cited, f"પાનું {exact}")], case)
                self.assertTrue(grounding.check_answer(answer, [passage]).ok, case)

    def test_exact_citation_is_left_alone(self):
        text, passage, exact = FAILED_CASES[0][1], FAILED_CASES[0][2], FAILED_CASES[0][3]
        answer = f"{text} (પાનું {exact})"
        self.assertEqual(grounding.snap_citations(answer, [passage]), (answer, []))

    def test_unplaceable_claim_is_not_moved(self):
        answer = "Vachik abhinaya is the play's dialogue (page 202)."
        self.assertEqual(grounding.snap_citations(answer, [P201]), (answer, []))

    def test_line_with_two_citations_is_not_moved(self):
        answer = f"{FAILED_CASES[0][1]} (પાનું 202) અને (પાનું 15)"
        self.assertEqual(grounding.snap_citations(answer, [P201, P15])[1], [])


if __name__ == "__main__":
    unittest.main()
