"""Login and book ownership, with two real Supabase accounts.

Skipped when Supabase is not configured. The accounts and books are temporary.
The client is never used as a context manager: that would run server startup,
which marks every upload in progress as failed, including real ones.
"""
import io
import unittest
import uuid
from unittest import mock

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

import tests.helpers  # noqa: F401  (no real provider keys)
import config
from api import auth
from api.main import app
from db import database

client = TestClient(app)
accounts = {}


def _admin(method, path, **kwargs):
    headers = {"apikey": config.SUPABASE_SECRET, "Authorization": f"Bearer {config.SUPABASE_SECRET}"}
    return httpx.request(method, f"{config.SUPABASE_URL}/auth/v1{path}", headers=headers, timeout=20, **kwargs)


def _new_account():
    email, password = f"test-{uuid.uuid4().hex[:12]}@example.com", uuid.uuid4().hex
    user = _admin("POST", "/admin/users", json={"email": email, "password": password,
                                                "email_confirm": True})
    user.raise_for_status()
    signed_in = httpx.post(f"{config.SUPABASE_URL}/auth/v1/token?grant_type=password",
                           headers={"apikey": config.SUPABASE_SECRET},
                           json={"email": email, "password": password}, timeout=20)
    signed_in.raise_for_status()
    return {"id": user.json()["id"],
            "headers": {"Authorization": f"Bearer {signed_in.json()['access_token']}"}}


CONFIGURED = bool(config.DATABASE_URL and config.SUPABASE_URL and config.SUPABASE_SECRET)


def setUpModule():
    if CONFIGURED:
        accounts["a"] = _new_account()
        accounts["b"] = _new_account()


def tearDownModule():
    for account in accounts.values():  # cascades to any book left behind
        _admin("DELETE", f"/admin/users/{account['id']}")
    database.close_db()


class Limit(unittest.TestCase):
    def setUp(self):
        auth._hits.clear()
        self.addCleanup(auth._hits.clear)

    def test_blocked_after_the_limit(self):
        auth.check_limit("u", "ask", 2)
        auth.check_limit("u", "ask", 2)
        with self.assertRaises(HTTPException) as caught:
            auth.check_limit("u", "ask", 2)
        self.assertEqual(caught.exception.status_code, 429)

    def test_counted_per_user_and_per_action(self):
        auth.check_limit("u", "ask", 1)
        auth.check_limit("other", "ask", 1)
        auth.check_limit("u", "upload", 1)

    def test_allowed_again_after_an_hour(self):
        with mock.patch("time.monotonic", return_value=1000.0):
            auth.check_limit("u", "ask", 1)
        with mock.patch("time.monotonic", return_value=1000.0 + 3600):
            auth.check_limit("u", "ask", 1)


class AuthServiceDown(unittest.TestCase):
    def test_outage_is_not_reported_as_a_bad_login(self):
        with mock.patch("httpx.get", side_effect=httpx.ConnectError("down")):
            response = client.get("/api/documents", headers={"Authorization": "Bearer x"})
        self.assertEqual(response.status_code, 503)


@unittest.skipUnless(CONFIGURED, "Supabase is not configured")
class Ownership(unittest.TestCase):
    def setUp(self):
        auth._hits.clear()
        self.addCleanup(auth._hits.clear)
        self.a, self.b = accounts["a"]["headers"], accounts["b"]["headers"]
        self.doc_id = self.make_book(accounts["a"]["id"])

    def make_book(self, owner):
        doc_id = f"test-{uuid.uuid4().hex[:12]}"
        self.addCleanup(database.delete_document, doc_id)
        database.create_document(doc_id, "x.pdf", "", user_id=owner)
        database.update_document(doc_id, status="ready")
        return doc_id

    def book_routes(self):
        return [("GET", f"/api/documents/{self.doc_id}", None),
                ("GET", f"/api/summary/{self.doc_id}", None),
                ("GET", f"/api/summary/{self.doc_id}/chapters", None),
                ("GET", f"/api/evaluate/{self.doc_id}?cached=true", None),
                ("GET", f"/api/evaluate/{self.doc_id}", None),
                ("POST", "/api/ask", {"doc_id": self.doc_id, "question": "કોણ?"}),
                ("DELETE", f"/api/documents/{self.doc_id}", None)]

    def test_every_route_except_health_needs_a_login(self):
        checked = 0
        for route in app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/api/") or path == "/api/health":
                continue
            for method in route.methods - {"HEAD", "OPTIONS"}:
                url = path.replace("{doc_id}", self.doc_id)
                response = client.request(method, url)
                self.assertEqual(response.status_code, 401, f"{method} {path}")
                checked += 1
        self.assertGreaterEqual(checked, 8)

    def test_health_stays_open(self):
        self.assertEqual(client.get("/api/health").status_code, 200)

    def test_invalid_token_is_refused(self):
        response = client.get("/api/documents", headers={"Authorization": "Bearer not-a-token"})
        self.assertEqual(response.status_code, 401)

    def test_other_user_gets_404_on_every_book_route(self):
        for method, url, body in self.book_routes():
            response = client.request(method, url, json=body, headers=self.b)
            self.assertEqual(response.status_code, 404, f"{method} {url}")
        self.assertIsNotNone(database.get_document(self.doc_id), "the book must survive")

    def test_other_user_cannot_tell_a_book_is_still_processing(self):
        database.update_document(self.doc_id, status="processing")
        response = client.post("/api/ask", json={"doc_id": self.doc_id, "question": "કોણ?"},
                               headers=self.b)
        self.assertEqual(response.status_code, 404)

    def test_book_with_no_owner_is_refused(self):
        doc_id = self.make_book(None)
        self.assertEqual(client.get(f"/api/documents/{doc_id}", headers=self.a).status_code, 404)

    def test_list_shows_only_your_own_books(self):
        other = self.make_book(accounts["b"]["id"])
        ids = lambda headers: {d["doc_id"] for d in client.get("/api/documents", headers=headers).json()}
        self.assertEqual(ids(self.a), {self.doc_id})
        self.assertEqual(ids(self.b), {other})

    def test_owner_can_read_and_ask(self):
        self.assertEqual(client.get(f"/api/documents/{self.doc_id}", headers=self.a).status_code, 200)
        with mock.patch("api.main.answer_question", return_value={"answer": "હા", "found": True}):
            response = client.post("/api/ask", json={"doc_id": self.doc_id, "question": "કોણ?"},
                                   headers=self.a)
        self.assertEqual(response.json()["answer"], "હા")

    def test_owner_can_delete(self):
        self.assertEqual(client.delete(f"/api/documents/{self.doc_id}", headers=self.a).status_code, 200)
        self.assertIsNone(database.get_document(self.doc_id))

    def test_upload_belongs_to_the_uploader(self):
        with mock.patch("api.main.process_document"):
            response = client.post("/api/upload", headers=self.b,
                                   files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")})
        doc_id = response.json()["doc_id"]
        self.addCleanup(database.delete_document, doc_id)
        self.addCleanup(lambda: (config.TEMP_UPLOAD_DIR / f"{doc_id}.pdf").unlink(missing_ok=True))
        self.assertEqual(str(database.get_document(doc_id)["user_id"]), accounts["b"]["id"])

    def test_live_evaluation_is_off_by_default(self):
        response = client.get(f"/api/evaluate/{self.doc_id}", headers=self.a)
        self.assertEqual(response.status_code, 403)

    def test_question_limit_applies(self):
        with mock.patch.object(config, "ASKS_PER_HOUR", 1), \
                mock.patch("api.main.answer_question", return_value={"answer": "હા"}):
            body = {"doc_id": self.doc_id, "question": "કોણ?"}
            self.assertEqual(client.post("/api/ask", json=body, headers=self.a).status_code, 200)
            self.assertEqual(client.post("/api/ask", json=body, headers=self.a).status_code, 429)

    def test_llm_outage_does_not_leak_details(self):
        with mock.patch("api.main.answer_question",
                        return_value={"llm_error": "secret provider detail"}):
            response = client.post("/api/ask", json={"doc_id": self.doc_id, "question": "કોણ?"},
                                   headers=self.a)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.text)

    def test_broken_pdf_error_does_not_show_server_paths(self):
        response = client.post("/api/upload?wait=true", headers=self.a,
                               files={"file": ("bad.pdf", io.BytesIO(b"not a pdf"), "application/pdf")})
        self.addCleanup(self.delete_failed_uploads)
        self.assertNotIn("/", response.json()["detail"])

    def delete_failed_uploads(self):
        for document in database.list_documents(accounts["a"]["id"]):
            if document["filename"] == "bad.pdf":
                database.delete_document(document["doc_id"])


if __name__ == "__main__":
    unittest.main()
