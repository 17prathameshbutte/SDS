import io
import os
import sqlite3
import tempfile
import unittest

from werkzeug.security import generate_password_hash

from app import create_app


class ComplaintTests(unittest.TestCase):
    def setUp(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_path = db_path
        self.app = create_app(testing=True, database_path=self.db_path)
        self.client = self.app.test_client()
        self.user_id = self.create_user(email="student@example.com", password="Student123")

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

    def create_user(self, name="Student", email="student@example.com", password="Student123", role="student"):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), role),
        )
        conn.commit()
        user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
        conn.close()
        return user_id

    def test_student_complaint_submission(self):
        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        response = self.client.post(
            "/report_issue",
            data={
                "title": "Broken socket",
                "category": "Electrical",
                "location": "Block A, Room 204",
                "description": "The socket is sparking and needs repair.",
                "image": (io.BytesIO(b"fakeimagecontent"), "fault.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Complaint submitted", response.data)

    def test_invalid_form_submissions(self):
        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        response = self.client.post(
            "/report_issue",
            data={
                "title": "",
                "category": "Electrical",
                "location": "",
                "description": "",
                "image": (io.BytesIO(b"fakeimage"), "fault.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Please fill in all required fields", response.data)

    def test_invalid_file_uploads(self):
        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        response = self.client.post(
            "/report_issue",
            data={
                "title": "Broken pipe",
                "category": "Plumbing",
                "location": "Block C, Room 101",
                "description": "Leak identified.",
                "image": (io.BytesIO(b"notanimage"), "doc.txt"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn(b"Only JPG and PNG image files are allowed", response.data)

    def test_student_access_to_own_tickets(self):
        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        response = self.client.get("/my_tickets")
        self.assertEqual(response.status_code, 200)

    def test_prevention_of_access_to_another_students_tickets(self):
        other_user = self.create_user(name="Other Student", email="other@example.com", password="Other123")
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO complaints (user_id, title, category, location, description, image_filename, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'Pending', CURRENT_TIMESTAMP)",
            (other_user, "Broken light", "Electrical", "Block B", "Light is off.", "sample.png"),
        )
        conn.commit()
        complaint_id = conn.execute("SELECT id FROM complaints WHERE title = 'Broken light'").fetchone()[0]
        conn.close()

        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        response = self.client.get(f"/ticket/{complaint_id}", follow_redirects=True)
        self.assertIn(b"another student", response.data)

    def test_cleaning_and_other_categories_are_available(self):
        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        response = self.client.get("/report_issue")
        self.assertIn(b"Cleaning", response.data)
        self.assertIn(b"Other", response.data)

    def test_student_can_change_or_remove_one_vote_per_issue(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO complaints
                (user_id, title, category, location, description, status, updated_at)
            VALUES (?, ?, ?, ?, ?, 'Pending', CURRENT_TIMESTAMP)
            """,
            (self.user_id, "Unclean washroom", "Cleaning", "Block A", "Needs cleaning."),
        )
        conn.commit()
        complaint_id = conn.execute(
            "SELECT id FROM complaints WHERE title = ?",
            ("Unclean washroom",),
        ).fetchone()[0]
        conn.close()

        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        first_vote = self.client.post(
            f"/issues/{complaint_id}/vote",
            data={"vote": "1"},
            follow_redirects=True,
        )
        self.assertIn(b"Upvote 1", first_vote.data)

        self.client.post(f"/issues/{complaint_id}/vote", data={"vote": "-1"})
        conn = sqlite3.connect(self.db_path)
        vote_after_change = conn.execute(
            "SELECT vote FROM complaint_votes WHERE complaint_id = ? AND user_id = ?",
            (complaint_id, self.user_id),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(vote_after_change, -1)

        self.client.post(f"/issues/{complaint_id}/vote", data={"vote": "-1"})
        conn = sqlite3.connect(self.db_path)
        remaining_votes = conn.execute(
            "SELECT COUNT(*) FROM complaint_votes WHERE complaint_id = ? AND user_id = ?",
            (complaint_id, self.user_id),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(remaining_votes, 0)

    def test_resolved_ticket_moves_to_archive_after_one_day(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO complaints
                (user_id, title, category, location, description, status, updated_at)
            VALUES (?, ?, ?, ?, ?, 'Resolved', datetime('now', '-2 days'))
            """,
            (self.user_id, "Old resolved leak", "Plumbing", "Block C", "Leak repaired."),
        )
        conn.commit()
        conn.close()

        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        tickets = self.client.get("/my_tickets")
        archive = self.client.get("/archive")
        self.assertNotIn(b"Old resolved leak", tickets.data)
        self.assertIn(b"Old resolved leak", archive.data)


if __name__ == "__main__":
    unittest.main()
