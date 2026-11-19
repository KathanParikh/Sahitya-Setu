"""The QA graph end to end, with retrieval and the LLM scripted."""
import unittest
from unittest import mock

from tests.helpers import P201, UNRELATED, ScriptedLLM, chunk
import config
from qa import graph, llm_client
from qa.prompt_builder import not_found_answer

NOT_FOUND = not_found_answer("gujarati")


def run(llm, search, question="નાટકમાં વાચિક અભિનય એટલે શું?", widen=None):
    # Widening reads neighbouring chunks from the database; by default it
    # changes nothing here, so these tests never touch the database.
    widen = widen or (lambda doc_id, chunks: list(chunks))
    with mock.patch.object(graph, "hybrid_search", side_effect=search), \
         mock.patch.object(graph, "widen_passages", side_effect=widen):
        return graph.answer_question("doc", question, app=graph.build_graph(llm))


def book(doc_id, query, top_k=None, **kw):
    """P201 only for queries that use the book's vocabulary."""
    return [P201] if "વાચિક" in query or "સંવાદ" in query else [UNRELATED]


class Paths(unittest.TestCase):
    def test_answer_in_book_first_try(self):
        llm = ScriptedLLM(relevant=lambda p: "વાચિક" in p,
                          answers=["“નટોની ક્રિયા કે કાર્ય એટલે નટોનો આંગિક અભિનય” (પાનું 201)"])
        r = run(llm, book)
        self.assertTrue(r["found"])
        self.assertEqual(r["rewrites_used"], 0)
        self.assertEqual([c["page_start"] for c in r["citations"]], [201])

    def test_absent_answer_falls_back_after_max_rewrites(self):
        llm = ScriptedLLM(relevant=lambda p: False)
        r = run(llm, lambda d, q, top_k=None, **kw: [UNRELATED], "કાબૂકીની શરૂઆત કોણે કરી?")
        self.assertFalse(r["found"])
        self.assertEqual(r["answer"], NOT_FOUND)
        self.assertEqual(r["rewrites_used"], config.MAX_QUERY_REWRITES)
        self.assertEqual(r["citations"], [])

    def test_vague_question_found_after_rewrite(self):
        llm = ScriptedLLM(relevant=lambda p: "વાચિક" in p, rewrite=lambda p: "નટોના સંવાદો",
                          answers=["“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 201)"])
        r = run(llm, book, "પેલું બોલવાનું શું કહેવાય?")
        self.assertTrue(r["found"])
        self.assertEqual(r["rewrites_used"], 1)
        self.assertEqual(r["queries_tried"][-1], "નટોના સંવાદો")


class Grounding(unittest.TestCase):
    def test_english_question_is_searched_in_gujarati(self):
        searches = []

        def search(doc_id, query, top_k=None, extra_vector_query=None):
            searches.append((query, extra_vector_query))
            return book(doc_id, query)

        llm = ScriptedLLM(relevant=lambda p: "વાચિક" in p,
                          translate=lambda p: "નાટકમાં વાચિક અભિનય એટલે શું?",
                          answers=["“નટોની ક્રિયા કે કાર્ય એટલે નટોનો આંગિક અભિનય” (page 201)"])
        r = run(llm, search, "What is vachik abhinay in drama?")
        self.assertTrue(r["found"])
        # Searched with the Gujarati translation, plus the English as a vector query.
        self.assertEqual(searches[0], ("નાટકમાં વાચિક અભિનય એટલે શું?",
                                       "What is vachik abhinay in drama?"))
        # Grading still judged the user's English question.
        grade_prompt = next(p for p in llm.prompts if '"grades"' in p)
        self.assertIn("Question: What is vachik abhinay in drama?", grade_prompt)

    def test_gujarati_question_is_not_translated(self):
        llm = ScriptedLLM(relevant=lambda p: "વાચિક" in p,
                          answers=["“નટોની ક્રિયા કે કાર્ય એટલે નટોનો આંગિક અભિનય” (પાનું 201)"])
        run(llm, book)
        self.assertFalse(any(p.startswith("Translate this question") for p in llm.prompts))

    def test_translation_in_english_falls_back_to_english_search(self):
        searches = []

        def search(doc_id, query, top_k=None, extra_vector_query=None):
            searches.append(query)
            return [UNRELATED]

        llm = ScriptedLLM(relevant=lambda p: False, translate=lambda p: "Sorry, I cannot.")
        r = run(llm, search, "Who started Kabuki?")
        self.assertEqual(searches[0], "Who started Kabuki?")
        self.assertIn("rejected", r["trace"][0])

    def test_answer_cut_at_a_chunk_boundary_is_found_by_widening(self):
        # The retrieved chunk has only half the scene; its neighbour has the rest.
        half = chunk("નાટકના સંવાદો એટલે", 201, 201, "doc:1")
        widened = []

        def widen(doc_id, chunks):
            widened.append([c.chunk_id for c in chunks])
            return [P201]

        llm = ScriptedLLM(relevant=lambda p: "વાચિક અભિનય" in p,
                          answers=["“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 201)"])
        r = run(llm, lambda d, q, top_k=None, **kw: [half], widen=widen)
        self.assertTrue(r["found"], r["trace"])
        self.assertEqual(r["rewrites_used"], 0)  # read further instead of searching again
        self.assertEqual(widened, [["doc:1"]])
        self.assertEqual([t["node"] for t in r["trace"]][:4], ["retrieve", "grade", "widen", "grade"])

    def test_widening_happens_once_per_question(self):
        calls = []
        llm = ScriptedLLM(relevant=lambda p: False)
        r = run(llm, lambda d, q, top_k=None, **kw: [UNRELATED],
                widen=lambda doc_id, chunks: calls.append(1) or list(chunks))
        self.assertFalse(r["found"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(r["rewrites_used"], config.MAX_QUERY_REWRITES)

    def test_regeneration_recovers_exact_answer(self):
        llm = ScriptedLLM(answers=["“નટો દ્વારા કરવામાં આવતી ક્રિયા, હાવભાવ” (પાનું 201)",
                                   "“નટોની ક્રિયા કે કાર્ય એટલે નટોનો આંગિક અભિનય” (પાનું 201)"])
        r = run(llm, book)
        self.assertTrue(r["found"], r["trace"])
        self.assertIn("નટોની ક્રિયા કે કાર્ય", r["answer"])
        regrounding = next(p for p in llm.prompts if "failed verification" in p)
        self.assertIn("quote not in passages", regrounding)

    def test_twice_ungrounded_answer_falls_back(self):
        llm = ScriptedLLM(answers=["“નટો દ્વારા કરવામાં આવતી ક્રિયા, હાવભાવ” (પાનું 201)"])
        r = run(llm, book)
        self.assertFalse(r["found"])
        self.assertEqual(r["answer"], NOT_FOUND)
        self.assertEqual(r["citations"], [])

    def test_invented_year_regenerates_to_not_found(self):
        llm = ScriptedLLM(answers=["કાબૂકી 1603માં શરૂ થયું (પાનું 201)", "NOT_FOUND"])
        r = run(llm, book)
        self.assertFalse(r["found"])
        self.assertEqual(r["citations"], [])

    def test_slipped_quote_corrected_without_regenerating(self):
        llm = ScriptedLLM(answers=["“નાટકનાં સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 201)"])
        r = run(llm, book)
        self.assertTrue(r["found"])
        self.assertIn("નાટકના સંવાદો", r["answer"])
        self.assertFalse(any("failed verification" in p for p in llm.prompts))


class ClaimVerificationInGraph(unittest.TestCase):
    PARAPHRASE = "વાચિક અભિનય એટલે નાટકના સંવાદો, અને આંગિક અભિનય એટલે નટોની ક્રિયા કે કાર્ય (પાનું 201)"

    def test_faithful_paraphrase_is_answered_after_verification(self):
        llm = ScriptedLLM(answers=[self.PARAPHRASE])
        r = run(llm, book)
        self.assertTrue(r["found"], r["trace"])
        self.assertEqual(r["answer"], self.PARAPHRASE)
        self.assertEqual(r["trace"][-1]["claims_llm_verified"], 1)

    def test_unsupported_claim_regenerates_then_falls_back(self):
        llm = ScriptedLLM(answers=[self.PARAPHRASE], supported=lambda c: False)
        r = run(llm, book)
        self.assertFalse(r["found"])
        self.assertEqual(r["answer"], NOT_FOUND)
        self.assertEqual(r["citations"], [])
        gen = [t for t in r["trace"] if t["node"] == "generate"][0]
        self.assertIn("claim not supported", gen["problems"][0])
        self.assertIn("claim not supported", gen["regenerated_problems"][0])

    def test_unsupported_claim_regenerates_into_a_verbatim_answer(self):
        # The verifier rejects the paraphrase and accepts the exact copy (an
        # exact copy is verified too, against the question).
        llm = ScriptedLLM(answers=[self.PARAPHRASE, "“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 201)"],
                          supported=lambda c: c.startswith("નાટકના સંવાદો એટલે"))
        r = run(llm, book)
        self.assertTrue(r["found"], r["trace"])
        self.assertIn("નાટકના સંવાદો", r["answer"])

    def test_elaboration_never_reaches_the_user(self):
        llm = ScriptedLLM(answers=["આંગિક અભિનય – નટો દ્વારા કરવામાં આવતી ક્રિયા, હાવભાવ, શરીરિક અભિવ્યક્તિ (પાનું 201-202)"])
        r = run(llm, book)
        self.assertFalse(r["found"])
        self.assertNotIn("હાવભાવ", r["answer"])

    def test_verifier_outage_is_a_service_error_not_an_answer(self):
        class Down(ScriptedLLM):
            def _complete(self, prompt, system, temperature):
                if '"claims"' in prompt:
                    raise llm_client.LLMError("verifier down")
                return super()._complete(prompt, system, temperature)
        r = run(Down(answers=[self.PARAPHRASE]), book)
        self.assertFalse(r["found"])
        self.assertIn("verifier down", r["llm_error"])
        self.assertEqual(r["citations"], [])


class PageCitationInGraph(unittest.TestCase):
    def test_range_citation_is_corrected_to_the_exact_page(self):
        llm = ScriptedLLM(answers=["“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનાં 201-202)"])
        r = run(llm, book)
        self.assertTrue(r["found"], r["trace"])
        self.assertIn("(પાનું 201)", r["answer"])
        self.assertEqual(r["trace"][-1]["citations_moved"], [("પાનાં 201-202", "પાનું 201")])

    def test_page_that_cannot_be_confirmed_falls_back(self):
        unreadable = chunk(P201.text, 301, 302, "nodoc:1")  # no page text to place it
        llm = ScriptedLLM(answers=["“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 302)"])
        r = run(llm, lambda d, q, top_k=None, **kw: [unreadable])
        self.assertFalse(r["found"])
        self.assertEqual(r["citations"], [])


class GradeAndRewriteNodes(unittest.TestCase):
    def state(self, docs):
        return {"question": "q", "original_question": "q", "documents": docs,
                "tried_queries": ["q"], "attempts": 0}

    def test_grade_keeps_only_passages_marked_relevant(self):
        llm = ScriptedLLM(relevant=lambda p: "વાચિક" in p)
        out = graph.grade_node(self.state([UNRELATED, P201, UNRELATED]), llm)
        self.assertEqual([c.chunk_id for c in out["relevant"]], [P201.chunk_id])

    def test_grade_judges_the_users_question_not_the_rewrite(self):
        prompts = []

        class Recording(ScriptedLLM):
            def _complete(self, prompt, system, temperature):
                prompts.append(prompt)
                return super()._complete(prompt, system, temperature)

        state = self.state([P201])
        state["original_question"] = "આ પુસ્તકનાં મુખ્ય પાત્રો કોણ છે?"
        state["question"] = "પુસ્તક મુખ્ય પાત્રો"
        graph.grade_node(state, Recording())
        self.assertIn("Question: આ પુસ્તકનાં મુખ્ય પાત્રો કોણ છે?", prompts[0])
        self.assertNotIn("Question: પુસ્તક મુખ્ય પાત્રો", prompts[0])

    def test_grade_ignores_out_of_range_passage_numbers(self):
        class Odd(ScriptedLLM):
            def _complete(self, prompt, system, temperature):
                return '{"grades": [{"passage": 7, "relevant": true}, {"passage": 0, "relevant": true}]}'
        out = graph.grade_node(self.state([P201]), Odd())
        self.assertEqual(out["relevant"], [])

    def test_grader_failure_is_visible_in_trace(self):
        # Existing design: if the grader cannot be reached, retrieved passages
        # go to the answer step (still behind NOT_FOUND and the grounding
        # check). The trace must say so; see the review's proposal.
        class Down(ScriptedLLM):
            def _complete(self, prompt, system, temperature):
                return "not json at all"
        out = graph.grade_node(self.state([P201]), Down())
        self.assertEqual(out["trace"][0].get("fallback"), "grader unavailable")

    def test_rewrite_falls_back_to_keywords_when_model_repeats_a_query(self):
        llm = ScriptedLLM(rewrite=lambda p: "q")
        out = graph.rewrite_node({"question": "q", "original_question": "શું વાચિક અભિનય છે?",
                                  "tried_queries": ["q"], "attempts": 0}, llm)
        self.assertNotEqual(out["question"], "q")
        self.assertEqual(out["attempts"], 1)

    def test_decide_after_grade(self):
        self.assertEqual(graph.decide_after_grade({"relevant": [P201], "attempts": 2}), "generate")
        self.assertEqual(graph.decide_after_grade({"relevant": [], "attempts": 0}), "rewrite")
        self.assertEqual(graph.decide_after_grade({"relevant": [], "attempts": config.MAX_QUERY_REWRITES}),
                         "fallback")


class Prompts(unittest.TestCase):
    """The rules the live evaluation depends on must stay in the prompts."""
    def test_grader_requires_the_passage_to_state_the_answer(self):
        from qa.prompt_builder import build_grade_prompt
        p = build_grade_prompt("q", [P201])
        self.assertIn("answered from this passage alone", p)
        self.assertIn("Every qualifier", p)
        self.assertIn("NOT enough", p)

    def test_rewriter_may_not_add_facts(self):
        from qa.prompt_builder import REWRITE_SYSTEM, build_rewrite_prompt
        self.assertIn("Do not add names, dates, numbers or facts", build_rewrite_prompt("q"))
        self.assertNotIn("Include likely proper nouns", build_rewrite_prompt("q"))
        self.assertIn("never add facts", REWRITE_SYSTEM)

    def test_answer_prompt_rules(self):
        from qa.prompt_builder import ANSWER_SYSTEM, build_answer_prompt
        gu = build_answer_prompt("વાચિક અભિનય એટલે શું?", [P201])
        en = build_answer_prompt("What is vachik abhinaya?", [P201])
        for p in (gu, en):
            self.assertIn("NOT_FOUND", p)
        # Fix 2: exact pages, located with the page marks.
        self.assertIn("ચોક્કસ પાનું", gu)
        self.assertIn("⟪પાનું N⟫", gu)
        self.assertIn("cite the exact page", en)
        self.assertIn("⟪પાનું N⟫", en)
        self.assertIn("character for character", ANSWER_SYSTEM)
        self.assertIn("Never define a term with itself", ANSWER_SYSTEM)




class CitationCorrection(unittest.TestCase):
    def test_right_claim_on_the_neighbouring_page_is_answered_with_the_exact_page(self):
        llm = ScriptedLLM(relevant=lambda p: "વાચિક" in p,
                          answers=["“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 202)"])
        r = run(llm, book)
        self.assertTrue(r["found"], r["trace"])
        self.assertIn("(પાનું 201)", r["answer"])
        # grade + answer + claim check; no regeneration needed
        self.assertEqual(len(llm.prompts), 3)

    def test_wrong_content_is_still_refused(self):
        llm = ScriptedLLM(relevant=lambda p: "વાચિક" in p, supported=lambda c: False,
                          answers=["નાટકના સંવાદો એટલે નટોનો આંગિક અભિનય (પાનું 202)"])
        r = run(llm, book)
        self.assertFalse(r["found"])


class GradePrompt(unittest.TestCase):
    def test_grader_sees_the_end_of_a_long_passage(self):
        from qa.prompt_builder import build_grade_prompt
        long = chunk("ક" * 1000 + " રાણાએ સોનાની એક એક વીંટી અપાવી.", 30)
        self.assertIn("વીંટી", build_grade_prompt("શું અપાવ્યું?", [long]))


if __name__ == "__main__":
    unittest.main()
