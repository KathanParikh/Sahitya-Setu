"""Chunk and vector storage, against the real database in SS_DATABASE_URL.

Skipped when no database is configured. Rows belong to random test books that
are deleted afterwards, so real books are never touched.
"""
import unittest
import uuid
from types import SimpleNamespace

import tests.helpers  # noqa: F401  (no real provider keys)
import config
from db import database
from indexing import vector_store


def tearDownModule():
    database.close_db()


def axis(i):
    """A unit vector along one axis: its cosine distance to the others is known."""
    return [1.0 if j == i else 0.0 for j in range(768)]


def chunk(i, text="લખાણ"):
    return SimpleNamespace(chunk_id=f"d:{i}", chunk_index=i, text=text, page_start=i + 1, page_end=i + 2,
                           chapter_index=0, chapter_title="પ્રકરણ", token_count=5)


@unittest.skipUnless(config.DATABASE_URL, "SS_DATABASE_URL is not set")
class Store(unittest.TestCase):
    def new_book(self):
        doc_id = f"test-{uuid.uuid4().hex[:12]}"
        self.addCleanup(database.delete_document, doc_id)
        database.create_document(doc_id, "x.pdf", "")
        return doc_id

    def setUp(self):
        self.doc_id = self.new_book()
        vector_store.add_chunks(self.doc_id, [chunk(0, "શૂન્ય"), chunk(1, "એક"), chunk(2, "બે")],
                                [axis(0), axis(1), axis(2)])

    def test_nearest_chunk_comes_first_with_its_similarity(self):
        hits = vector_store.search(self.doc_id, axis(1), top_k=3)
        self.assertEqual(hits[0]["chunk_id"], "d:1")
        self.assertAlmostEqual(hits[0]["score"], 1.0, places=5)
        self.assertAlmostEqual(hits[1]["score"], 0.0, places=5)
        self.assertEqual([h["rank"] for h in hits], [1, 2, 3])

    def test_top_k_limits_results(self):
        self.assertEqual(len(vector_store.search(self.doc_id, axis(1), top_k=2)), 2)

    def test_results_carry_the_page_and_chapter(self):
        meta = vector_store.search(self.doc_id, axis(2), top_k=1)[0]["metadata"]
        self.assertEqual((meta["page_start"], meta["page_end"], meta["chapter_title"]), (3, 4, "પ્રકરણ"))

    def test_search_never_returns_another_books_chunks(self):
        other = self.new_book()
        vector_store.add_chunks(other, [chunk(0, "બીજું પુસ્તક")], [axis(1)])
        self.assertEqual(vector_store.search(other, axis(1))[0]["text"], "બીજું પુસ્તક")
        self.assertEqual(len(vector_store.search(other, axis(1), top_k=10)), 1)
        self.assertNotIn("બીજું પુસ્તક", [h["text"] for h in vector_store.search(self.doc_id, axis(1))])

    def test_get_by_ids(self):
        rows = vector_store.get_by_ids(self.doc_id, ["d:2", "d:0", "missing"])
        self.assertEqual(set(rows), {"d:0", "d:2"})
        self.assertEqual(rows["d:2"]["text"], "બે")

    def test_all_chunks_are_in_reading_order(self):
        rows = vector_store.get_all_chunks(self.doc_id)
        self.assertEqual([r["metadata"]["chunk_index"] for r in rows], [0, 1, 2])

    def test_failed_insert_stores_nothing(self):
        other = self.new_book()
        with self.assertRaises(Exception):
            vector_store.add_chunks(other, [chunk(0), chunk(0)], [axis(0), axis(1)])  # duplicate id
        self.assertEqual(vector_store.get_all_chunks(other), [])

    def test_mismatched_lengths_are_rejected(self):
        with self.assertRaises(ValueError):
            vector_store.add_chunks(self.doc_id, [chunk(5)], [])

    def test_deleting_the_book_removes_its_chunks(self):
        database.delete_document(self.doc_id)
        self.assertEqual(vector_store.get_all_chunks(self.doc_id), [])


if __name__ == "__main__":
    unittest.main()
