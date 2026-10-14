import os
import sqlite3
import tempfile
import unittest

from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app


class AuthTests(unittest.TestCase):
    def setUp(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_path = db_path
        self.app = create_app(testing=True, database_path=self.db_path)
        self.client = self.app.test_client()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except FileNotFoundError:
            pass

    def create_user(self, name="Test User", email="user@example.com", password="Password1", role="student"):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), role),
        )
        conn.commit()
        user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
        conn.close()
        return user_id

    def test_home_page_loading(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"CampusFix", response.data)

    def test_student_registration(self):
        response = self.client.post(
            "/register",
            data={
                "name": "Student One",
                "email": "student1@example.com",
                "password": "Password123",
                "confirm_password": "Password123",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Registration successful", response.data)

    def test_duplicate_email_handling(self):
        self.client.post(
            "/register",
            data={
                "name": "Student One",
                "email": "student1@example.com",
                "password": "Password123",
                "confirm_password": "Password123",
            },
        )
        response = self.client.post(
            "/register",
            data={
                "name": "Student Two",
                "email": "student1@example.com",
                "password": "Password123",
                "confirm_password": "Password123",
            },
        )
        self.assertIn(b"already exists", response.data)

    def test_login_success_and_failure(self):
        self.create_user(email="login@example.com", password="Secret123")

        failure = self.client.post(
            "/login",
            data={"email": "login@example.com", "password": "Wrongpass"},
            follow_redirects=True,
        )
        self.assertIn(b"Invalid email or password", failure.data)

        success = self.client.post(
            "/login",
            data={"email": "login@example.com", "password": "Secret123"},
            follow_redirects=True,
        )
        self.assertEqual(success.status_code, 200)
        self.assertIn(b"Welcome", success.data)

    def test_password_hashing(self):
        user_id = self.create_user(email="hash@example.com", password="Secret999")
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        self.assertTrue(check_password_hash(row[0], "Secret999"))

    def test_student_route_access_restrictions(self):
        self.create_user(email="student@example.com", password="Student123")
        self.client.post("/login", data={"email": "student@example.com", "password": "Student123"})
        response = self.client.get("/admin", follow_redirects=True)
        self.assertIn(b"not allowed", response.data)


if __name__ == "__main__":
    unittest.main()
