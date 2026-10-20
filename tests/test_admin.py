import os
import sqlite3
import tempfile
import unittest

from werkzeug.security import generate_password_hash

from app import create_app


class AdminTests(unittest.TestCase):
    def setUp(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_path = db_path
        self.app = create_app(testing=True, database_path=self.db_path)
        self.client = self.app.test_client()
        self.student_id = self.create_user(email="student@example.com", password="Student123")
        self.admin_id = self.create_user(email="admin@example.com", password="Admin123", role="admin")

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

    def create_user(self, name="User", email="user@example.com", password="Password1", role="student"):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), role),
        )
        conn.commit()
        user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
        conn.close()
        return user_id

    def test_admin_route_restrictions(self):
        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        response = self.client.get("/admin", follow_redirects=True)
        self.assertIn(b"not allowed", response.data)

    def test_admin_status_update_and_history(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO complaints (user_id, title, category, location, description, image_filename, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'Pending', CURRENT_TIMESTAMP)",
            (self.student_id, "Broken chair", "Furniture", "Room 10", "Chair damaged.", "chair.png"),
        )
        conn.commit()
        complaint_id = conn.execute("SELECT id FROM complaints WHERE title = ?", ("Broken chair",)).fetchone()[0]
        conn.close()

        self.client.post("/login", data={"email": "admin@example.com", "password": "Admin123"})
        response = self.client.post(
            f"/admin/update_status/{complaint_id}",
            data={"status": "In Progress"},
            follow_redirects=True,
        )
        self.assertIn(b"Status updated", response.data)

        conn = sqlite3.connect(self.db_path)
        updated = conn.execute("SELECT status FROM complaints WHERE id = ?", (complaint_id,)).fetchone()[0]
        history_count = conn.execute("SELECT COUNT(*) FROM status_history WHERE complaint_id = ?", (complaint_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(updated, "In Progress")
        self.assertGreater(history_count, 0)

    def add_complaint(self, title, location="Block A"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "INSERT INTO complaints (user_id, title, category, location, description, status, updated_at) "
            "VALUES (?, ?, 'Plumbing', ?, 'Details.', 'Pending', CURRENT_TIMESTAMP)",
            (self.student_id, title, location),
        )
        conn.commit()
        complaint_id = cursor.lastrowid
        conn.close()
        return complaint_id

    def test_admin_can_search_by_displayed_ticket_id(self):
        first = self.add_complaint("Leaky tap")
        second = self.add_complaint("Broken window", location="Block B")
        self.assertEqual((first, second), (1, 2))
        self.client.post("/login", data={"email": "admin@example.com", "password": "Admin123"})

        for term in ("CF-00002", "cf-00002", "CF00002", "00002", "2"):
            html = self.client.get("/admin", query_string={"search": term}).data
            self.assertIn(b"Broken window", html, term)
            self.assertNotIn(b"Leaky tap", html, term)

    def test_admin_search_still_matches_title_and_location(self):
        self.add_complaint("Leaky tap", location="Block A")
        self.add_complaint("Broken window", location="Library")
        self.client.post("/login", data={"email": "admin@example.com", "password": "Admin123"})
        by_title = self.client.get("/admin", query_string={"search": "leaky"}).data
        by_location = self.client.get("/admin", query_string={"search": "library"}).data
        self.assertIn(b"Leaky tap", by_title)
        self.assertNotIn(b"Broken window", by_title)
        self.assertIn(b"Broken window", by_location)

    def test_admin_search_handles_huge_numbers_without_error(self):
        self.add_complaint("Leaky tap")
        self.client.post("/login", data={"email": "admin@example.com", "password": "Admin123"})
        response = self.client.get("/admin", query_string={"search": "9" * 40})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
