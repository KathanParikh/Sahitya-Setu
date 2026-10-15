"""Gujarati BM25 tokenization and the in-memory upgrade of v1 indexes."""
import os
import pickle
import tempfile
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


class Upgrade(unittest.TestCase):
    def test_v1_pickle_retokenized_from_store_without_rewriting(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "doc.pkl")
            with open(path, "wb") as fh:  # what the old tokenizer stored
                pickle.dump({"version": 1, "chunk_ids": ["a", "b", "c"],
                             "corpus_tokens": [["વ", "ચ", "ક"], ["ન", "ટક"], ["ગ"]]}, fh)
            with open(path, "rb") as fh:
                before = fh.read()
            rows = {"a": {"text": "વાચિક અભિનય"}, "b": {"text": "નાટક રંગમંચ"},
                    "c": {"text": "દિગ્દર્શક"}}
            with mock.patch("indexing.vector_store.get_by_ids", return_value=rows):
                idx = BM25Index.load(path, "doc")
            self.assertEqual(idx.corpus_tokens, [["વાચિક", "અભિનય"], ["નાટક", "રંગમંચ"], ["દિગ્દર્શક"]])
            self.assertEqual(idx.search("વાચિક")[0].chunk_id, "a")
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), before)

    def test_new_saves_are_current_version(self):
        with tempfile.TemporaryDirectory() as d:
            path = BM25Index(["a"], [["x"]]).save(os.path.join(d, "doc.pkl"))
            with open(path, "rb") as fh:
                self.assertEqual(pickle.load(fh)["version"], bm25_index.TOKENIZER_VERSION)
            with mock.patch("indexing.vector_store.get_by_ids") as store:
                BM25Index.load(path, "doc")
                store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
