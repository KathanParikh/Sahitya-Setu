"""The Postgres store, against the real database in SS_DATABASE_URL.

Skipped when no database is configured. Every row belongs to a random test
book that is deleted afterwards, so real books are never touched.
"""
import unittest
import uuid
from types import SimpleNamespace

import tests.helpers  # noqa: F401  (no real provider keys)
import config
from db import database


def tearDownModule():
    database.close_db()


@unittest.skipUnless(config.DATABASE_URL, "SS_DATABASE_URL is not set")
class Store(unittest.TestCase):
    def setUp(self):
        self.doc_id = f"test-{uuid.uuid4().hex[:12]}"
        self.addCleanup(database.delete_document, self.doc_id)
        database.create_document(self.doc_id, "પુસ્તક.pdf", "/tmp/x.pdf")

    def test_new_document_is_read_back(self):
        document = database.get_document(self.doc_id)
        self.assertEqual(document["filename"], "પુસ્તક.pdf")
        self.assertEqual(document["status"], "pending")
        self.assertEqual(document["extraction_stats"], {})

    def test_unknown_document_is_none(self):
        self.assertIsNone(database.get_document("no-such-book"))

    def test_update_stores_stats_as_json(self):
        database.update_document(self.doc_id, chunk_count=7, extraction_stats={"ocr_pages": 3})
        document = database.get_document(self.doc_id)
        self.assertEqual(document["chunk_count"], 7)
        self.assertEqual(document["extraction_stats"], {"ocr_pages": 3})

    def test_status_keeps_progress_and_error(self):
        database.set_status(self.doc_id, "failed", progress="failed", error="તૂટ્યું")
        document = database.get_document(self.doc_id)
        self.assertEqual((document["status"], document["error"]), ("failed", "તૂટ્યું"))

    def test_interrupted_document_is_marked_failed(self):
        database.set_status(self.doc_id, "processing", progress="chunking")
        self.assertEqual(database.fail_interrupted_documents(self.doc_id), 1)
        document = database.get_document(self.doc_id)
        self.assertEqual(document["status"], "failed")
        self.assertIn("upload the book again", document["error"])

    def test_saving_chapters_replaces_the_old_list(self):
        chapter = lambda i, t: SimpleNamespace(index=i, title=t, start_page=i + 1, end_page=i + 2)
        database.save_chapters(self.doc_id, [chapter(0, "જૂનું"), chapter(1, "બીજું")])
        database.save_chapters(self.doc_id, [chapter(0, "નવું")])
        self.assertEqual([c["title"] for c in database.get_chapters(self.doc_id)], ["નવું"])

    def test_saving_no_chapters_clears_them(self):
        database.save_chapters(self.doc_id, [])
        self.assertEqual(database.get_chapters(self.doc_id), [])

    def test_saving_a_summary_again_overwrites_it(self):
        database.save_summary(self.doc_id, "full", "પહેલો")
        database.save_summary(self.doc_id, "full", "બીજો")
        self.assertEqual(database.get_summary(self.doc_id, "full"), "બીજો")

    def test_chapter_summaries_carry_the_chapter_title(self):
        database.save_chapters(self.doc_id, [SimpleNamespace(index=0, title="પ્રકરણ", start_page=1, end_page=2)])
        database.save_summary(self.doc_id, "chapter", "સાર", chapter_index=0)
        row = database.get_chapter_summaries(self.doc_id)[0]
        self.assertEqual((row["title"], row["content"]), ("પ્રકરણ", "સાર"))

    def test_latest_evaluation_is_returned_as_a_dict(self):
        database.save_evaluation(self.doc_id, {"run": 1}, 1)
        database.save_evaluation(self.doc_id, {"run": 2}, 2)
        self.assertEqual(database.get_latest_evaluation(self.doc_id)["metrics"], {"run": 2})

    def test_deleting_a_book_removes_its_rows(self):
        database.save_chapters(self.doc_id, [SimpleNamespace(index=0, title="પ્રકરણ", start_page=1, end_page=2)])
        database.save_summary(self.doc_id, "full", "સાર")
        database.delete_document(self.doc_id)
        self.assertEqual(database.get_chapters(self.doc_id), [])
        self.assertIsNone(database.get_summary(self.doc_id, "full"))


if __name__ == "__main__":
    unittest.main()
