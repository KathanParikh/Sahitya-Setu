"""PDF storage, against the real bucket. Skipped when Storage is not configured.

Objects use random test names and are deleted afterwards.
"""
import tempfile
import unittest
import uuid
from pathlib import Path

import httpx

import tests.helpers  # noqa: F401  (no real provider keys)
import config
from db import file_store


@unittest.skipUnless(config.SUPABASE_URL and config.SUPABASE_SECRET, "Storage is not configured")
class Bucket(unittest.TestCase):
    CONTENT = b"%PDF-1.4 test \xe0\xaa\x97 " * 100

    def setUp(self):
        self.doc_id = f"test-{uuid.uuid4().hex[:12]}"
        self.addCleanup(file_store.delete, self.doc_id)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "book.pdf"
        self.path.write_bytes(self.CONTENT)

    def test_uploaded_file_comes_back_unchanged(self):
        self.assertEqual(file_store.upload(self.doc_id, self.path), f"{self.doc_id}.pdf")
        self.assertEqual(file_store.download(self.doc_id), self.CONTENT)

    def test_uploading_again_replaces_the_file(self):
        file_store.upload(self.doc_id, self.path)
        self.path.write_bytes(b"%PDF new")
        file_store.upload(self.doc_id, self.path)
        self.assertEqual(file_store.download(self.doc_id), b"%PDF new")

    def test_deleted_file_is_gone(self):
        file_store.upload(self.doc_id, self.path)
        file_store.delete(self.doc_id)
        with self.assertRaises(httpx.HTTPStatusError):
            file_store.download(self.doc_id)

    def test_deleting_a_missing_file_is_not_an_error(self):
        file_store.delete(self.doc_id)

    def test_bucket_refuses_requests_without_the_key(self):
        file_store.upload(self.doc_id, self.path)
        base = f"{config.SUPABASE_URL}/storage/v1/object"
        for url in (f"{base}/{file_store.BUCKET}/{self.doc_id}.pdf",
                    f"{base}/public/{file_store.BUCKET}/{self.doc_id}.pdf"):
            self.assertGreaterEqual(httpx.get(url, timeout=30).status_code, 400, url)


if __name__ == "__main__":
    unittest.main()
