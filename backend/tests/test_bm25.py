"""Gujarati BM25 tokenization and the in-memory upgrade of v1 indexes."""
import unittest
from unittest import mock

from indexing import bm25_index
from indexing.bm25_index import BM25Index, tokenize


class Tokenizer(unittest.TestCase):
    def test_vowel_signs_stay_in_word(self):
        self.assertEqual(tokenize("નાટકમાં વાચિક અભિનય અને આંગિક અભિનય એટલે શું?"),
                         ["નાટકમાં", "વાચિક", "અભિનય", "આંગિક", "અભિનય", "એટલે"])

    def test_virama_conjuncts_and_punctuation(self):
        self.assertEqual(tokenize("સ્ટાનિસ્લાવ્સ્કી, ‘આહાર્ય’ (Folk) ૧૯૩૦।"),
                         ["સ્ટાનિસ્લાવ્સ્કી", "આહાર્ય", "folk", "૧૯૩૦"])

    def test_zero_width_joiner_does_not_split(self):
        self.assertEqual(tokenize("ક્ષ‍ત્ર"), ["ક્ષત્ર"])

    def test_stopwords_match(self):
        self.assertNotIn("અને", tokenize("રામ અને સીતા"))


class Index(unittest.TestCase):
    ROWS = [{"chunk_id": "a", "text": "વાચિક અભિનય"}, {"chunk_id": "b", "text": "નાટક રંગમંચ"},
            {"chunk_id": "c", "text": "દિગ્દર્શક"}]

    def setUp(self):
        self.addCleanup(bm25_index.delete_index, "doc")

    def test_built_from_stored_chunk_text(self):
        with mock.patch("indexing.vector_store.get_all_chunks", return_value=self.ROWS):
            index = bm25_index.get_index("doc")
        self.assertEqual(index.search("વાચિક")[0].chunk_id, "a")

    def test_second_question_does_not_read_the_chunks_again(self):
        with mock.patch("indexing.vector_store.get_all_chunks", return_value=self.ROWS) as store:
            first = bm25_index.get_index("doc")
            self.assertIs(bm25_index.get_index("doc"), first)
        store.assert_called_once()

    def test_book_without_chunks_has_no_index(self):
        with mock.patch("indexing.vector_store.get_all_chunks", return_value=[]):
            self.assertIsNone(bm25_index.get_index("doc"))

    def test_database_failure_means_no_index_not_a_crash(self):
        with mock.patch("indexing.vector_store.get_all_chunks", side_effect=RuntimeError("down")):
            self.assertIsNone(bm25_index.get_index("doc"))

    def test_chunk_with_only_stopwords_does_not_break_the_index(self):
        index = BM25Index.build(["a", "b", "c"], ["અને", "વાચિક", "નાટક"])
        self.assertEqual(index.search("વાચિક")[0].chunk_id, "b")


if __name__ == "__main__":
    unittest.main()
