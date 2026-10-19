"""Page text stored at ingestion is what the citation check reads back."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tests.helpers  # noqa: F401  (no real provider keys)
import config
from processing.pdf_extractor import Page
from qa import pages


class StoredPages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(config, "PAGES_DIR", Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(pages._book_pages.cache_clear)

    def test_stored_text_is_read_back_without_touching_the_pdf(self):
        pages.save_book_pages("bk", [Page(1, "પહેલું પાનું", "ocr"), Page(2, "બીજું પાનું", "ocr")])
        with mock.patch("processing.pdf_extractor.extract_pages") as extract, \
                mock.patch("processing.pdf_extractor.ocr_page") as ocr:
            self.assertEqual(pages.pdf_page_text("bk", 2), "બીજું પાનું")
            extract.assert_not_called()
            ocr.assert_not_called()

    def test_empty_stored_page_is_not_ocrd_again(self):
        pages.save_book_pages("bk", [Page(1, "", "empty")])
        with mock.patch("processing.pdf_extractor.ocr_page") as ocr:
            self.assertIsNone(pages.pdf_page_text("bk", 1))
            ocr.assert_not_called()

    def test_saving_again_replaces_cached_text(self):
        pages.save_book_pages("bk", [Page(1, "જૂનું", "ocr")])
        self.assertEqual(pages.pdf_page_text("bk", 1), "જૂનું")
        pages.save_book_pages("bk", [Page(1, "નવું", "ocr")])
        self.assertEqual(pages.pdf_page_text("bk", 1), "નવું")

    def test_delete_removes_the_store(self):
        pages.save_book_pages("bk", [Page(1, "લખાણ", "ocr")])
        pages.delete_book_pages("bk")
        self.assertFalse((Path(self.tmp.name) / "bk.json").exists())


if __name__ == "__main__":
    unittest.main()
