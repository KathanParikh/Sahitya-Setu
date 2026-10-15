import unittest

from tests.helpers import P15, P56, P201, chunk, set_page
from qa import grounding


class Quotes(unittest.TestCase):
    def test_exact_quote_passes_unchanged(self):
        a = "- “નટોની ક્રિયા કે કાર્ય એટલે નટોનો આંગિક અભિનય” (પાનું 201)"
        r = grounding.check_answer(a, [P201])
        self.assertTrue(r.ok, r.problems)
        self.assertEqual(r.answer, a)

    def test_live_test1_anusvara_slip_is_snapped_to_book_text(self):
        # The model wrote નાટકનાં; the book has નાટકના.
        a = "- “નાટકનાં સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 201)"
        r = grounding.check_answer(a, [P201])
        self.assertTrue(r.ok, r.problems)
        self.assertIn("“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય”", r.answer)
        self.assertNotIn("નાટકનાં", r.answer)

    def test_paraphrase_inside_quotes_fails(self):
        r = grounding.check_answer("“નટો દ્વારા કરવામાં આવતી ક્રિયા, હાવભાવ” (પાનું 201)", [P201])
        self.assertFalse(r.ok)
        self.assertIn("quote not in passages", r.problems[0])

    def test_nested_title_inside_a_quote_checks_the_whole_quote(self):
        a = "“‘અંધાયુગ’ની રજૂઆત જાપાનીઝ ક્લાસિકલ નાટ્યશૈલી ‘નોહ’ અને ‘કાબૂકી’માં કરવામાં આવી” (પાનું 15)"
        self.assertTrue(grounding.check_answer(a, [P15]).ok)
        altered = a.replace("જાપાનીઝ", "ચીની")
        r = grounding.check_answer(altered, [P15])
        self.assertIn("quote not in passages", " ".join(r.problems))

    def test_brackets_in_the_book_text_still_match_exactly(self):
        c = chunk("સાઈકલૉરામા એટલે સટેજની પાછળ (છેવાડેની ભીંતની આગળ) ગોઠવવામાં આવતો વિશાળ સફેદ પડદો.", 70, 70, "doc:70b")
        claim = grounding.extract_claims("સાઈકલૉરામા એટલે સટેજની પાછળ (છેવાડેની ભીંતની આગળ) ગોઠવવામાં આવતો વિશાળ સફેદ પડદો (પાનું 70, પ્રકરણ 2)", [c])[0]
        self.assertTrue(claim.verbatim)

    def test_short_titles_and_apostrophes_are_not_quotes(self):
        one_page = chunk(P15.text, 15, 15, "doc:15b")
        self.assertTrue(grounding.check_answer("It's ‘અંધાયુગ’, the actor's view (page 15).", [one_page]).ok)


class Pages(unittest.TestCase):
    def test_page_outside_passages_fails(self):
        r = grounding.check_answer("વાચિક અભિનય (પાનું 197)", [P201])
        self.assertFalse(r.ok)

    def test_citation_formats_parse(self):
        for a, expected in (("(પાનું 201‑202)", [201, 202]), ("(પાનાં ૨૦૧-૨૦૨)", [201, 202]),
                            ("(page 202)", [202]), ("(pages 201–202)", [201, 202]),
                            ("(પાનું ૪૨, પ્રકરણ 3)", [42])):
            self.assertEqual(grounding._cited_pages("x " + a), expected, a)

    def test_range_reaching_a_page_not_shown_fails(self):
        r = grounding.check_answer("“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનાં 200-201)", [P201])
        self.assertIn("cites page 200", " ".join(r.problems))


class FactTokens(unittest.TestCase):
    def test_invented_year_caught(self):
        r = grounding.check_answer("કાબૂકીની શરૂઆત 1603માં થઈ (પાનું 15)", [P15])
        self.assertIn("not in passages: 1603", r.problems)

    def test_invented_year_in_gujarati_digits_caught(self):
        self.assertFalse(grounding.check_answer("૧૬૦૩માં (પાનું ૧૫)", [P15]).ok)

    def test_invented_english_name_in_gujarati_answer_caught(self):
        r = grounding.check_answer("કાબૂકીની શરૂઆત Izumo no Okuni એ કરી (પાનું 15)", [P15])
        self.assertIn("not in passages: Okuni", r.problems)

    def test_numbers_and_english_titles_from_book_pass(self):
        a = "છેલ્લાં 50 વર્ષમાં ઈબસનના When the Dead Awaken ની ભજવણી મણિપુરી શૈલીમાં થઈ (પાનું 15)"
        self.assertTrue(grounding.check_answer(a, [P15]).ok)

    def test_list_markers_and_chapter_numbers_ignored(self):
        a = "1. અંધાયુગ નોહ શૈલીમાં (પાનું 15, પ્રકરણ 1)\n2. મણિપુરી શૈલી (પાનું 15)"
        r = grounding.check_answer(a, [P15])
        self.assertTrue(r.ok, r.problems)

    def test_live_test3_answer_with_pdf_hyphenation_passes(self):
        r = grounding.check_answer("‘commanding image’ (પાનું 56)", [P56])
        self.assertTrue(r.ok, r.problems)

    def test_english_answer_prose_allowed_numbers_still_checked(self):
        one_page = chunk(P15.text, 15, 15, "doc:15b")
        self.assertTrue(grounding.check_answer("Andha Yug was staged in the Noh style (page 15).", [one_page]).ok)
        self.assertFalse(grounding.check_answer("It was staged in 1971 (page 15).", [one_page]).ok)


class StrictRules(unittest.TestCase):
    """Rules added in the pre-commit audit."""
    P163 = chunk("એટલે જ સંસકૃત નાટકમાં વાચિક, આંગિકની સાથે સાથે ‘આહાર્ય અભિનય’ શબ્દપ્રયોગ થાય છે",
                 162, 163, "doc:297")
    set_page("doc", 162, "ભારતીય શાસ્ત્રીય નૃત્યોમાં અનેક હસ્તમુદ્રાઓ આવે છે.")
    set_page("doc", 163, P163.text)

    def test_every_claim_line_needs_a_citation(self):
        r = grounding.check_answer("નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય", [P201])
        self.assertIn("no page citation", r.problems[0])

    def test_uncited_second_line_fails(self):
        a = "“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 201)\nઆંગિક એટલે ક્રિયા"
        self.assertFalse(grounding.check_answer(a, [P201]).ok)

    def test_introductory_line_needs_no_citation(self):
        a = "પુસ્તક મુજબ:\n“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 201)"
        r = grounding.check_answer(a, [P201])
        self.assertTrue(r.ok, r.problems)

    def test_quote_must_be_on_its_own_lines_cited_page(self):
        r = grounding.check_answer("“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 163)", [P201, self.P163])
        self.assertIn("not the cited", r.problems[0])

    def test_one_swapped_word_is_not_auto_corrected(self):
        a = ("“નાટકના સંવાદો એટલે નટોનો આંગિક અભિનય અને નટોની ક્રિયા કે કાર્ય એટલે "
             "નટોનો આંગિક અભિનય” (પાનું 201)")
        r = grounding.check_answer(a, [P201])
        self.assertFalse(r.ok)
        self.assertEqual(r.snapped, [])

    def test_correction_limit_is_two_characters(self):
        two = "“નાટકનાં સંવાદો એટલે નટોનોો વાચિક અભિનય” (પાનું 201)"     # 2 extra chars
        three = "“નાટકનાં સંવાદોો એટલે નટોનોો વાચિક અભિનય” (પાનું 201)"  # 3 extra chars
        self.assertTrue(grounding.check_answer(two, [P201]).ok)
        self.assertFalse(grounding.check_answer(three, [P201]).ok)

    def test_quote_mark_style_and_edge_punctuation_are_normalized(self):
        c = chunk("‘પ્રમુખ છબી’ એટલે નાટકમાંથી દૃશયાતમક માર્ગેે નીકળતો એકંદર ભાવ કે અસર.", 275, 276, "doc:511")
        set_page("doc", 275, c.text)
        set_page("doc", 276, "નાટક જયાં ભજવાય છે તે રંગમંચ વિશે જાણવું જરૂરી છે.")
        r = grounding.check_answer("“‘પ્રમુખ છબી’ એટલે નાટકમાંથી દૃશયાતમક માર્ગેે નીકળતો એકંદર ભાવ કે અસર.” (પાનું 275)", [c])
        self.assertTrue(r.ok, r.problems)
        self.assertEqual(r.snapped, [])

    def test_match_form_never_alters_letters(self):
        self.assertEqual(grounding.match_form(" “નાટકના  સંવાદો”. "), "નાટકના સંવાદો")
        self.assertNotEqual(grounding.match_form("નાટકનાં"), grounding.match_form("નાટકના"))


class ClaimsLexical(unittest.TestCase):
    """Unquoted claims are checked against the passages their line cites."""

    def test_unquoted_elaboration_is_rejected(self):
        a = "આંગિક અભિનય – નટો દ્વારા કરવામાં આવતી ક્રિયા, હાવભાવ, શરીરિક અભિવ્યક્તિ (પાનું 201-202)"
        self.assertFalse(grounding.check_answer(a, [P201]).ok)

    def test_unquoted_invented_gujarati_name_is_rejected(self):
        self.assertFalse(grounding.check_answer("કાબૂકીની શરૂઆત ઓકુની નામની નર્તકીએ કરી હતી (પાનું 15)", [P15]).ok)

    def test_rejection_names_the_unsupported_words(self):
        r = grounding.check_answer("કાબૂકીની શરૂઆત ઓકુની નામની નર્તકીએ કરી હતી (પાનું 15)", [P15])
        self.assertIn("ઓકુની", " ".join(r.problems))

    def test_faithful_reordering_passes_lexically(self):
        a = "વાચિક અભિનય એટલે નાટકના સંવાદો, અને આંગિક અભિનય એટલે નટોની ક્રિયા કે કાર્ય (પાનું 201)"
        r = grounding.check_answer(a, [P201])
        self.assertTrue(r.ok, r.problems)

    def test_words_are_matched_only_against_the_lines_cited_passage(self):
        # Every word is in P201, but the line cites page 15.
        a = "નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય (પાનું 15)"
        self.assertFalse(grounding.check_answer(a, [P201, P15]).ok)

    def test_inflection_and_dropped_virama_count_as_the_same_word(self):
        c = chunk("સાઈકલૉરામા એટલે સટેજની પાછળ ગોઠવવામાં આવતો વિશાળ સફેદ પડદો.", 69, 70)
        claim = grounding.extract_claims("સાઈકલૉરામા એટલે સ્ટેજની પાછળનો વિશાળ સફેદ પડદો (પાનાં 69-70)", [c])[0]
        self.assertEqual(claim.novel, [])

    def test_verbatim_claim_is_marked_and_needs_no_semantic_check(self):
        claim = grounding.extract_claims("નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય (પાનું 201)", [P201])[0]
        self.assertTrue(claim.verbatim)

    def test_one_new_word_is_left_to_the_semantic_check(self):
        claims = grounding.extract_claims("‘અંધાયુગ’ની રજૂઆત ઓકુનીએ ‘નોહ’ અને ‘કાબૂકી’માં કરી (પાનું 15)", [P15])
        self.assertTrue(grounding.check_answer("‘અંધાયુગ’ની રજૂઆત ઓકુનીએ ‘નોહ’ અને ‘કાબૂકી’માં કરી (પાનું 15)", [P15]).ok)
        self.assertFalse(claims[0].verbatim)
        self.assertEqual(claims[0].novel, ["ઓકુનીએ"])


class ExactCopyOnlySkipsVerifier(unittest.TestCase):
    """Fix 1: a one- or two-character change can reverse the meaning, so only an
    exact copy (after match_form) bypasses the semantic check."""
    FULL = ("નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય અને નટોની ક્રિયા કે કાર્ય એટલે નટોનો આંગિક "
            "અભિનય - આ બંને વચ્ચેે સુમેળ સાધીને દિગ્દર્શક એક સંયુકત પ્રભાવકારી છબી ઉપસાવે છે")

    def claim(self, text):
        return grounding.extract_claims(text + " (પાનું 201)", [P201])[0]

    def test_exact_copy_skips(self):
        self.assertTrue(self.claim(self.FULL).verbatim)

    def test_exact_copy_with_different_quote_marks_and_end_punctuation_skips(self):
        self.assertTrue(self.claim("“" + self.FULL + ".”").verbatim)

    def test_added_negation_goes_to_verifier(self):
        self.assertFalse(self.claim(self.FULL.replace("સુમેળ સાધીને", "સુમેળ ન સાધીને")).verbatim)

    def test_changed_subject_goes_to_verifier(self):
        # નટોનો (the actors') -> નટીનો (the actress's): one letter.
        self.assertFalse(self.claim(self.FULL.replace("નટોનો વાચિક", "નટીનો વાચિક")).verbatim)

    def test_changed_name_goes_to_verifier(self):
        self.assertFalse(self.claim(self.FULL.replace("દિગ્દર્શક", "લેખક")).verbatim)

    def test_swapped_meaning_goes_to_verifier(self):
        swapped = self.FULL.replace("વાચિક", "TMP").replace("આંગિક", "વાચિક").replace("TMP", "આંગિક")
        self.assertFalse(self.claim(swapped).verbatim)

    def test_one_dropped_anusvara_goes_to_verifier(self):
        # Harmless here, but not provably so: the verifier decides.
        self.assertFalse(self.claim(self.FULL.replace("નાટકના", "નાટકનાં", 1)).verbatim)

    def test_altered_meanings_reach_the_verifier_and_its_verdict_decides(self):
        from tests.helpers import ScriptedLLM
        for altered in (self.FULL.replace("સુમેળ સાધીને", "સુમેળ ન સાધીને"),
                        self.FULL.replace("નટોનો વાચિક", "નટીનો વાચિક"),
                        self.FULL.replace("દિગ્દર્શક", "લેખક")):
            llm = ScriptedLLM(supported=lambda c: False)
            problems, checked = grounding.verify_claims(altered + " (પાનું 201)", [P201], llm)
            self.assertEqual(checked, 1, altered)
            self.assertTrue(problems, altered)


class ExactPageCitations(unittest.TestCase):
    """Fix 2: a chunk's page range does not prove which page a claim is on."""
    Q = "“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય”"

    def test_exact_page_accepted(self):
        r = grounding.check_answer(f"{self.Q} (પાનું 201)", [P201])
        self.assertTrue(r.ok, r.problems)

    def test_whole_chunk_range_rejected_when_text_is_on_one_page(self):
        r = grounding.check_answer(f"{self.Q} (પાનાં 201-202)", [P201])
        self.assertIn("is on page(s) [201]", " ".join(r.problems))

    def test_wrong_page_inside_the_range_rejected(self):
        r = grounding.check_answer(f"{self.Q} (પાનું 202)", [P201])
        self.assertIn("is on page(s) [201]", " ".join(r.problems))

    def test_sentence_across_a_page_break_needs_both_pages(self):
        c = chunk("‘સાઈકલૉરામા’ એટલે સટેજની પાછળ (છેવાડેની ભીંતની આગળ) ગોઠવવામાં આવતો વિશાળ સફેદ પડદો.",
                  69, 70, "doc:122")
        set_page("doc", 69, "Flexible Stage. ‘સાઈકલૉરામા’ એટલે સટેજની પાછળ (છેવાડેની ભીંતની આગળ)")
        set_page("doc", 70, "ગોઠવવામાં આવતો વિશાળ સફેદ પડદો. આ સફેદ પડદો કેટલાક નાટ્યગૃહોમાં ગોળાકાર હોય છે.")
        a = "“‘સાઈકલૉરામા’ એટલે સટેજની પાછળ (છેવાડેની ભીંતની આગળ) ગોઠવવામાં આવતો વિશાળ સફેદ પડદો”"
        self.assertTrue(grounding.check_answer(a + " (પાનાં 69-70)", [c]).ok)
        self.assertFalse(grounding.check_answer(a + " (પાનું 69)", [c]).ok)
        self.assertFalse(grounding.check_answer(a + " (પાનું 70)", [c]).ok)

    def test_gujarati_paraphrase_is_placed_by_its_words(self):
        a = "વાચિક અભિનય એટલે નાટકના સંવાદો (પાનું 201)"
        self.assertTrue(grounding.check_answer(a, [P201]).ok)
        self.assertFalse(grounding.check_answer(a.replace("201", "202"), [P201]).ok)

    def test_unreadable_page_text_rejects_the_citation(self):
        c = chunk(P201.text, 301, 302, "nodoc:1")  # no page text available
        r = grounding.check_answer(f"{self.Q} (પાનું 301)", [c])
        self.assertIn("cannot read", " ".join(r.problems))

    def test_english_paraphrase_of_a_two_page_passage_cannot_be_placed(self):
        r = grounding.check_answer("Vachik abhinaya is the play's dialogue (page 201).", [P201])
        self.assertIn("cannot establish", " ".join(r.problems))

    def test_one_page_passage_needs_no_page_text(self):
        c = chunk(P201.text, 301, 301, "nodoc:2")
        self.assertTrue(grounding.check_answer(f"{self.Q} (પાનું 301)", [c]).ok)

    def test_markers_show_the_model_where_a_page_begins(self):
        from qa import pages
        c = chunk("પહેલા પાનાનું છેલ્લું વાક્ય છે. બીજા પાનાની શરૂઆતનું આ વાક્ય પૂરતું લાંબું છે.", 88, 89, "doc:88")
        set_page("doc", 88, "પહેલા પાનાનું છેલ્લું વાક્ય છે.")
        set_page("doc", 89, "બીજા પાનાની શરૂઆતનું આ વાક્ય પૂરતું લાંબું છે.")
        self.assertIn("છે. ⟪પાનું 89⟫ બીજા", pages.with_page_markers(c))

    def test_no_marker_when_page_opening_is_not_found(self):
        from qa import pages
        self.assertNotIn("⟪", pages.with_page_markers(P201))  # page 202 text is not in P201


class ClaimsSemantic(unittest.TestCase):
    """verify_claims with a scripted verifier: what is sent, and how verdicts are read."""

    def run_verify(self, answer, chunks, supported=lambda c: True, raw=None):
        from tests.helpers import ScriptedLLM
        llm = ScriptedLLM(supported=supported)
        if raw is not None:
            llm._complete = lambda prompt, system, temperature: (llm.prompts.append(prompt) or raw)
        problems, checked = grounding.verify_claims(answer, chunks, llm)
        return problems, checked, llm.prompts

    def test_verbatim_answer_makes_no_verifier_call(self):
        problems, checked, prompts = self.run_verify("“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 201)", [P201])
        self.assertEqual((problems, checked, prompts), ([], 0, []))

    def test_paraphrase_is_sent_with_its_passage_and_unmatched_words(self):
        a = "‘અંધાયુગ’ની રજૂઆત ઓકુનીએ ‘નોહ’ અને ‘કાબૂકી’માં કરી (પાનું 15)"
        problems, checked, prompts = self.run_verify(a, [P15, P201])
        self.assertEqual(checked, 1)
        self.assertIn("ઓકુનીએ", prompts[0])
        self.assertIn(P15.text[:30], prompts[0])
        self.assertNotIn(P201.text[:30], prompts[0])  # only the cited passage

    def test_unsupported_verdict_is_a_problem(self):
        a = "‘અંધાયુગ’ની રજૂઆત ઓકુનીએ ‘નોહ’ અને ‘કાબૂકી’માં કરી (પાનું 15)"
        problems, _, _ = self.run_verify(a, [P15], supported=lambda c: False)
        self.assertIn("claim not supported", problems[0])

    def test_meaning_swap_with_book_words_goes_to_verifier(self):
        # Every word is the book's, but વાચિક/આંગિક are swapped.
        a = "નાટકના સંવાદો એટલે નટોનો આંગિક અભિનય (પાનું 201)"
        self.assertTrue(grounding.check_answer(a, [P201]).ok)
        problems, checked, _ = self.run_verify(a, [P201], supported=lambda c: "આંગિક" not in c)
        self.assertEqual(checked, 1)
        self.assertTrue(problems)

    def test_missing_verdict_counts_as_unsupported(self):
        a = "વાચિક અભિનય એટલે નાટકના સંવાદો, અને આંગિક અભિનય એટલે નટોની ક્રિયા કે કાર્ય (પાનું 201-202)"
        problems, _, _ = self.run_verify(a, [P201], raw='{"claims": []}')
        self.assertIn("no verdict", problems[0])

    def test_non_boolean_verdict_counts_as_unsupported(self):
        a = "વાચિક અભિનય એટલે નાટકના સંવાદો, અને આંગિક અભિનય એટલે નટોની ક્રિયા કે કાર્ય (પાનું 201-202)"
        problems, _, _ = self.run_verify(a, [P201], raw='{"claims": [{"claim": 1, "supported": "yes"}]}')
        self.assertTrue(problems)


if __name__ == "__main__":
    unittest.main()
