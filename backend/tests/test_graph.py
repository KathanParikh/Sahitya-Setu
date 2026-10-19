"""The QA graph end to end, with retrieval and the LLM scripted."""
import unittest
from unittest import mock

from tests.helpers import P201, UNRELATED, ScriptedLLM, chunk
import config
from qa import graph, llm_client
from qa.prompt_builder import not_found_answer

NOT_FOUND = not_found_answer("gujarati")


def run(llm, search, question="નાટકમાં વાચિક અભિનય એટલે શું?"):
    with mock.patch.object(graph, "hybrid_search", side_effect=search):
        return graph.answer_question("doc", question, app=graph.build_graph(llm))


def book(doc_id, query, top_k=None):
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
        r = run(llm, lambda d, q, top_k=None: [UNRELATED], "કાબૂકીની શરૂઆત કોણે કરી?")
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
    def test_regeneration_recovers_exact_answer(self):
        llm = ScriptedLLM(answers=["“નટો દ્વારા કરવામાં આવતી ક્રિયા, હાવભાવ” (પાનું 201)",
                                   "“નટોની ક્રિયા કે કાર્ય એટલે નટોનો આંગિક અભિનય” (પાનું 201)"])
        r = run(llm, book)
        self.assertTrue(r["found"], r["trace"])
        self.assertIn("નટોની ક્રિયા કે કાર્ય", r["answer"])
        self.assertIn("failed verification", llm.prompts[-1])
        self.assertIn("quote not in passages", llm.prompts[-1])

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
        llm = ScriptedLLM(answers=[self.PARAPHRASE, "“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 201)"],
                          supported=lambda c: False)
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
        r = run(llm, lambda d, q, top_k=None: [unreadable])
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


class RunQA(unittest.TestCase):
    def test_brief_shape(self):
        llm = ScriptedLLM(answers=["“નટોની ક્રિયા કે કાર્ય એટલે નટોનો આંગિક અભિનય” (પાનું 201)"])
        with mock.patch.object(graph, "hybrid_search", side_effect=book):
            r = graph.run_qa("doc", "વાચિક?", book_title="Test", app=graph.build_graph(llm))
        self.assertEqual(set(r), {"answer", "found", "sources", "question_used", "retries"})
        self.assertEqual(r["sources"][0]["page_no"], 201)


if __name__ == "__main__":
    unittest.main()


class CitationCorrection(unittest.TestCase):
    def test_right_claim_on_the_neighbouring_page_is_answered_with_the_exact_page(self):
        llm = ScriptedLLM(relevant=lambda p: "વાચિક" in p,
                          answers=["“નાટકના સંવાદો એટલે નટોનો વાચિક અભિનય” (પાનું 202)"])
        r = run(llm, book)
        self.assertTrue(r["found"], r["trace"])
        self.assertIn("(પાનું 201)", r["answer"])
        self.assertEqual(len(llm.prompts), 2)  # grade + answer; no regeneration needed

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
