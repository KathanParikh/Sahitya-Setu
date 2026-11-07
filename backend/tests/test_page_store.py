"""Page text stored at ingestion is what the citation check reads back.

Runs against the real database in SS_DATABASE_URL; skipped when there is none.
"""
import unittest
import uuid
from unittest import mock

import tests.helpers  # noqa: F401  (no real provider keys)
import config
from db import database
from processing.pdf_extractor import Page
from qa import pages


def tearDownModule():
    database.close_db()


@unittest.skipUnless(config.DATABASE_URL, "SS_DATABASE_URL is not set")
class StoredPages(unittest.TestCase):
    def setUp(self):
        self.doc_id = f"test-{uuid.uuid4().hex[:12]}"
        self.addCleanup(database.delete_document, self.doc_id)
        self.addCleanup(pages._book_pages.cache_clear)
        database.create_document(self.doc_id, "x.pdf", "")

    def test_stored_text_is_read_back(self):
        pages.save_book_pages(self.doc_id, [Page(1, "પહેલું પાનું", "ocr"), Page(2, "બીજું પાનું", "ocr")])
        self.assertEqual(pages.stored_page_text(self.doc_id, 2), "બીજું પાનું")

    def test_empty_or_missing_page_is_none(self):
        pages.save_book_pages(self.doc_id, [Page(1, "", "empty")])
        self.assertIsNone(pages.stored_page_text(self.doc_id, 1))
        self.assertIsNone(pages.stored_page_text(self.doc_id, 2))

    def test_saving_again_replaces_cached_text(self):
        pages.save_book_pages(self.doc_id, [Page(1, "જૂનું", "ocr"), Page(2, "બીજું", "ocr")])
        self.assertEqual(pages.stored_page_text(self.doc_id, 1), "જૂનું")
        pages.save_book_pages(self.doc_id, [Page(1, "નવું", "ocr")])
        self.assertEqual(pages.stored_page_text(self.doc_id, 1), "નવું")
        self.assertIsNone(pages.stored_page_text(self.doc_id, 2))

    def test_delete_removes_the_pages(self):
        pages.save_book_pages(self.doc_id, [Page(1, "લખાણ", "ocr")])
        pages.delete_book_pages(self.doc_id)
        self.assertIsNone(pages.stored_page_text(self.doc_id, 1))

    def test_answering_never_touches_the_pdf(self):
        pages.save_book_pages(self.doc_id, [Page(1, "લખાણ", "ocr")])
        with mock.patch("processing.pdf_extractor.extract_pages") as extract, \
                mock.patch("processing.pdf_extractor.ocr_page") as ocr:
            pages.stored_page_text(self.doc_id, 1)
            extract.assert_not_called()
            ocr.assert_not_called()


class DatabaseDown(unittest.TestCase):
    def test_unreachable_database_means_unknown_text_not_a_crash(self):
        pages._book_pages.cache_clear()
        with mock.patch("db.database.get_pages", side_effect=RuntimeError("down")):
            self.assertIsNone(pages.stored_page_text("any", 1))
        pages._book_pages.cache_clear()


if __name__ == "__main__":
    unittest.main()
