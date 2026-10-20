import io
import os
import re
import shutil
import sqlite3
import tempfile
import unittest

from werkzeug.security import generate_password_hash

from app import create_app
from config import resolve_secret_key


class SecurityBase(unittest.TestCase):
    """Shared setup: one app, an owner, another student and an admin. Holds no tests itself."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.upload_dir = tempfile.mkdtemp()
        self.app = create_app(testing=True, database_path=self.db_path, upload_folder=self.upload_dir)
        self.client = self.app.test_client()
        self.owner_id = self.create_user("owner@example.com")
        self.other_id = self.create_user("other@example.com")
        self.admin_id = self.create_user("admin@example.com", role="admin")

    def tearDown(self):
        os.remove(self.db_path)
        shutil.rmtree(self.upload_dir, ignore_errors=True)

    def create_user(self, email, role="student"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (email.split("@")[0], email, generate_password_hash("Passw0rd1"), role),
        )
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id

    def login(self, email):
        self.client.post("/login", data={"email": email, "password": "Passw0rd1"})

    def add_complaint_with_image(self, filename="photo.png", content=b"image-bytes"):
        with open(os.path.join(self.upload_dir, filename), "wb") as handle:
            handle.write(content)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "INSERT INTO complaints (user_id, title, category, location, description, image_filename, status, updated_at) "
            "VALUES (?, 'Broken light', 'Electrical', 'Block B', 'Dark.', ?, 'Pending', CURRENT_TIMESTAMP)",
            (self.owner_id, filename),
        )
        conn.commit()
        complaint_id = cursor.lastrowid
        conn.close()
        return complaint_id



class SecurityTests(SecurityBase):
    """Session handling and access control for uploaded images."""

    # --- Bug 2: a session for a user that no longer exists -------------------------------
    def test_deleted_user_session_is_sent_to_login_instead_of_crashing(self):
        self.login("other@example.com")
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM users WHERE id = ?", (self.other_id,))
        conn.commit()
        conn.close()

        for path in ("/dashboard", "/archive", "/ticket/1", "/report_issue", "/issues", "/my_tickets"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302, path)
            self.assertIn("/login", response.headers["Location"], path)

    def test_stale_session_is_cleared_after_redirect(self):
        self.login("other@example.com")
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM users WHERE id = ?", (self.other_id,))
        conn.commit()
        conn.close()
        self.client.get("/dashboard")
        with self.client.session_transaction() as flask_session:
            self.assertNotIn("user_id", flask_session)

    # --- Bug 3: uploaded images are no longer public ------------------------------------------
    def test_uploads_require_login(self):
        self.add_complaint_with_image()
        response = self.client.get("/uploads/photo.png")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_owner_and_admin_can_view_the_image(self):
        self.add_complaint_with_image(content=b"owner-image")
        self.login("owner@example.com")
        response = self.client.get("/uploads/photo.png")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"owner-image")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        response.close()
        self.client.get("/logout")

        self.login("admin@example.com")
        admin_response = self.client.get("/uploads/photo.png")
        self.assertEqual(admin_response.status_code, 200)
        admin_response.close()

    def test_other_students_cannot_view_the_image(self):
        self.add_complaint_with_image()
        self.login("other@example.com")
        self.assertEqual(self.client.get("/uploads/photo.png").status_code, 404)

    def test_unknown_or_unlisted_files_return_404_even_if_they_exist_on_disk(self):
        with open(os.path.join(self.upload_dir, "orphan.png"), "wb") as handle:
            handle.write(b"x")
        self.login("admin@example.com")
        self.assertEqual(self.client.get("/uploads/orphan.png").status_code, 404)
        self.assertEqual(self.client.get("/uploads/missing.png").status_code, 404)

    def test_path_traversal_is_rejected(self):
        self.add_complaint_with_image()
        self.login("admin@example.com")
        for path in ("/uploads/../app.py", "/uploads/..%2Fapp.py", "/uploads/%2e%2e/config.py"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


TOKEN_PATTERN = re.compile(rb'name="csrf_token" value="([^"]+)"')


class CsrfTests(SecurityBase):
    """CSRF protection is switched on here (the other tests run with it off for simplicity)."""

    def setUp(self):
        super().setUp()
        self.app.config["WTF_CSRF_ENABLED"] = True

    def token_from(self, path):
        match = TOKEN_PATTERN.search(self.client.get(path).data)
        self.assertIsNotNone(match, f"no csrf_token field found on {path}")
        return match.group(1).decode()

    def db_value(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        value = conn.execute(sql, params).fetchone()
        conn.close()
        return value[0] if value else None

    def add_open_complaint(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "INSERT INTO complaints (user_id, title, category, location, description, status, updated_at) "
            "VALUES (?, 'Leaky tap', 'Plumbing', 'Block A', 'Dripping.', 'Pending', CURRENT_TIMESTAMP)",
            (self.owner_id,),
        )
        conn.commit()
        complaint_id = cursor.lastrowid
        conn.close()
        return complaint_id

    def test_every_post_form_contains_a_csrf_token(self):
        self.add_open_complaint()
        for path in ("/login", "/register"):
            self.assertRegex(self.client.get(path).data.decode(), r'name="csrf_token"', path)

        self.login_with_token("owner@example.com")
        for path in ("/report_issue", "/issues"):
            self.assertRegex(self.client.get(path).data.decode(), r'name="csrf_token"', path)
        self.client.get("/logout")

        self.login_with_token("admin@example.com")
        self.assertRegex(self.client.get("/admin").data.decode(), r'name="csrf_token"')

    def login_with_token(self, email):
        token = self.token_from("/login")
        return self.client.post("/login", data={"email": email, "password": "Passw0rd1", "csrf_token": token})

    def test_login_without_token_is_rejected(self):
        response = self.client.post("/login", data={"email": "owner@example.com", "password": "Passw0rd1"},
                                    follow_redirects=True)
        self.assertIn(b"form session has expired or is invalid", response.data)
        with self.client.session_transaction() as flask_session:
            self.assertNotIn("user_id", flask_session)

    def test_login_with_valid_token_works(self):
        response = self.login_with_token("owner@example.com")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers["Location"])

    def test_login_with_wrong_token_is_rejected(self):
        self.client.get("/login")
        response = self.client.post("/login", data={"email": "owner@example.com", "password": "Passw0rd1",
                                                    "csrf_token": "not-a-real-token"})
        with self.client.session_transaction() as flask_session:
            self.assertNotIn("user_id", flask_session)
        self.assertEqual(response.status_code, 302)

    def test_registration_without_token_creates_no_account(self):
        self.client.post("/register", data={"name": "New", "email": "new@example.com",
                                            "password": "Passw0rd1", "confirm_password": "Passw0rd1"})
        self.assertIsNone(self.db_value("SELECT id FROM users WHERE email = ?", ("new@example.com",)))

    def test_admin_status_change_without_token_is_rejected(self):
        complaint_id = self.add_open_complaint()
        self.login_with_token("admin@example.com")
        self.client.post(f"/admin/update_status/{complaint_id}", data={"status": "Resolved"})
        self.assertEqual(self.db_value("SELECT status FROM complaints WHERE id = ?", (complaint_id,)), "Pending")

        token = self.token_from("/admin")
        self.client.post(f"/admin/update_status/{complaint_id}", data={"status": "Resolved", "csrf_token": token})
        self.assertEqual(self.db_value("SELECT status FROM complaints WHERE id = ?", (complaint_id,)), "Resolved")

    def test_vote_without_token_is_rejected_and_with_token_is_recorded(self):
        complaint_id = self.add_open_complaint()
        self.login_with_token("other@example.com")
        self.client.post(f"/issues/{complaint_id}/vote", data={"vote": "1"})
        self.assertIsNone(self.db_value("SELECT vote FROM complaint_votes WHERE complaint_id = ?", (complaint_id,)))

        token = self.token_from("/issues")
        self.client.post(f"/issues/{complaint_id}/vote", data={"vote": "1", "csrf_token": token})
        self.assertEqual(self.db_value("SELECT vote FROM complaint_votes WHERE complaint_id = ?", (complaint_id,)), 1)

    def test_complaint_submission_without_token_is_rejected(self):
        self.login_with_token("owner@example.com")
        response = self.client.post(
            "/report_issue",
            data={"title": "T", "category": "Other", "location": "L", "description": "D",
                  "image": (io.BytesIO(b"x"), "a.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(os.listdir(self.upload_dir), [])
        self.assertIsNone(self.db_value("SELECT id FROM complaints WHERE title = 'T'"))


class SecretKeyTests(unittest.TestCase):
    def test_missing_or_placeholder_keys_become_random_keys(self):
        for value in (None, "", "   ", "your-secret-key-here", "dev-secret-key-change-me"):
            key, is_random = resolve_secret_key(value)
            self.assertTrue(is_random, repr(value))
            self.assertGreaterEqual(len(key), 32)
        self.assertNotEqual(resolve_secret_key(None)[0], resolve_secret_key(None)[0])

    def test_a_real_key_is_used_unchanged(self):
        self.assertEqual(resolve_secret_key("my-long-private-key"), ("my-long-private-key", False))


class AdminNavigationTests(SecurityBase):
    """Student-only links are hidden from admins (decision 4)."""

    def test_admin_does_not_see_student_links_or_vote_buttons(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO complaints (user_id, title, category, location, description, status, updated_at) "
            "VALUES (?, 'Leaky tap', 'Plumbing', 'Block A', 'Dripping.', 'Pending', CURRENT_TIMESTAMP)",
            (self.owner_id,),
        )
        conn.commit()
        conn.close()
        self.login("admin@example.com")
        for path in ("/admin", "/issues", "/archive"):
            html = self.client.get(path).data
            self.assertNotIn(b"My Tickets", html, path)
            self.assertNotIn(b"Report Issue", html, path)
            self.assertNotIn(b"Report an Issue", html, path)
            self.assertIn(b"Admin Dashboard", html, path)
        self.assertNotIn(b"Upvote", self.client.get("/issues").data)

    def test_student_still_sees_student_links_and_vote_buttons(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO complaints (user_id, title, category, location, description, status, updated_at) "
            "VALUES (?, 'Leaky tap', 'Plumbing', 'Block A', 'Dripping.', 'Pending', CURRENT_TIMESTAMP)",
            (self.owner_id,),
        )
        conn.commit()
        conn.close()
        self.login("owner@example.com")
        html = self.client.get("/issues").data
        for text in (b"My Tickets", b"Report Issue", b"Report an Issue", b"Upvote", b"Downvote"):
            self.assertIn(text, html, text)
        self.assertNotIn(b"Admin Dashboard", html)

    def test_admin_missing_ticket_goes_to_admin_dashboard(self):
        self.login("admin@example.com")
        response = self.client.get("/ticket/999")
        self.assertIn("/admin", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
