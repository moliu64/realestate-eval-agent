"""HTTP contract tests driven by Starlette's in-process TestClient.

The tests redirect session/auth storage into a temporary directory and never
call a real model provider, so they are deterministic and CI-friendly.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from pathlib import Path

_TMP = tempfile.TemporaryDirectory()
os.environ["AUTH_USERS_JSON"] = (
    '{"admin":{"password":"admin-test-password","role":"admin"}}'
)
os.environ["SESSIONS_DIR"] = str(Path(_TMP.name) / "sessions")
os.environ["AUTH_USERS_FILE"] = str(Path(_TMP.name) / "auth_users.json")

from app.config import load_config  # noqa: E402

load_config.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


class ApiContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    # -- authentication -----------------------------------------------------
    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "realestate-eval-agent")

    def test_anonymous_auth_probe(self) -> None:
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["authenticated"])

    def test_sessions_require_login(self) -> None:
        self.assertEqual(self.client.get("/api/sessions").status_code, 401)
        self.assertEqual(self.client.post("/api/sessions").status_code, 401)

    def test_register_and_login_flow(self) -> None:
        username = f"reviewer_{uuid.uuid4().hex[:8]}"
        registered = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "review-pass-123", "confirm_password": "review-pass-123"},
        )
        self.assertEqual(registered.status_code, 200, registered.text)
        self.assertTrue(registered.json()["registered"])

        duplicate = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "review-pass-123", "confirm_password": "review-pass-123"},
        )
        self.assertEqual(duplicate.status_code, 409)

        failed_login = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "wrong-password"},
        )
        self.assertEqual(failed_login.status_code, 401)

        login = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "review-pass-123"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["role"], "user")

        me = self.client.get("/api/auth/me")
        self.assertTrue(me.json()["authenticated"])
        self.assertEqual(me.json()["username"], username)

        logout = self.client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 200)
        self.assertFalse(self.client.get("/api/auth/me").json()["authenticated"])

    # -- sessions -----------------------------------------------------------
    def test_session_lifecycle(self) -> None:
        self._login("admin", "admin-test-password")

        created = self.client.post("/api/sessions")
        self.assertEqual(created.status_code, 200, created.text)
        session_id = created.json()["id"]

        listing = self.client.get("/api/sessions")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(session_id, [item["id"] for item in listing.json()])

        patched = self.client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "测试会话", "fixed_fields": {"area": 100, "property_usage": "住宅"}},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["title"], "测试会话")

        fetched = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(fetched.json()["fixed_fields"]["area"], 100)

        deleted = self.client.delete(f"/api/sessions/{session_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/api/sessions/{session_id}").status_code, 404)

    # -- admin --------------------------------------------------------------
    def test_admin_page_redirects_anonymous_visitors(self) -> None:
        response = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/")

        self._login("admin", "admin-test-password")
        page = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["content-type"])

    def test_admin_guard(self) -> None:
        self.assertEqual(self.client.get("/admin/access").status_code, 401)

        self._login("admin", "admin-test-password")
        access = self.client.get("/admin/access")
        self.assertEqual(access.status_code, 200, access.text)
        self.assertTrue(access.json()["authorized"])
        self.assertEqual(self.client.get("/admin/documents").status_code, 200)

    def test_non_admin_cannot_manage_knowledge_base(self) -> None:
        username = f"viewer_{uuid.uuid4().hex[:8]}"
        self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "review-pass-123", "confirm_password": "review-pass-123"},
        )
        self._login(username, "review-pass-123")
        self.assertEqual(self.client.get("/admin/access").status_code, 403)
        self.assertEqual(self.client.get("/admin/documents").status_code, 403)
        self.assertEqual(self.client.get("/admin", follow_redirects=False).status_code, 302)

    def _login(self, username: str, password: str) -> None:
        response = self.client.post("/api/auth/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)


def tearDownModule() -> None:
    _TMP.cleanup()


if __name__ == "__main__":
    unittest.main()
