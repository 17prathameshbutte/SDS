import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from database import create_admin_user, ensure_default_admin, get_db, init_db


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.db_path = os.path.join(self.folder, "test.db")

    def tearDown(self):
        for name in os.listdir(self.folder):
            os.remove(os.path.join(self.folder, name))
        os.rmdir(self.folder)

    def rows(self, sql, params=()):
        conn = sqlite3.connect(self.db_path)
        result = conn.execute(sql, params).fetchall()
        conn.close()
        return result

    def add_user(self, email, role):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES ('Existing', ?, ?, ?)",
            (email, generate_password_hash("OldPassw0rd"), role),
        )
        conn.commit()
        conn.close()

    def test_init_db_creates_all_tables_and_can_run_twice(self):
        init_db(self.db_path)
        init_db(self.db_path)
        tables = {row[0] for row in self.rows("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({"users", "complaints", "status_history", "complaint_votes"} <= tables)

    def test_old_priority_labels_are_renamed(self):
        init_db(self.db_path)
        self.add_user("s@example.com", "student")
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO complaints (user_id, title, category, location, description, ai_priority) "
            "VALUES (1, 't', 'Other', 'l', 'd', 'Urgent')"
        )
        conn.commit()
        conn.close()
        init_db(self.db_path)
        self.assertEqual(self.rows("SELECT ai_priority FROM complaints"), [("Critical",)])

    # --- foreign keys are enforced for the app's own connections -------------------------------
    def test_foreign_keys_are_enforced_by_the_app_connection(self):
        app = create_app(testing=True, database_path=self.db_path, upload_folder=self.folder)
        with app.app_context():
            conn = get_db()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO complaints (user_id, title, category, location, description) "
                    "VALUES (999, 't', 'Other', 'l', 'd')"
                )

    # --- admin bootstrap ---------------------------------------------------------------------------
    def test_default_admin_is_created_from_environment(self):
        init_db(self.db_path)
        env = {"ADMIN_EMAIL": "Boss@Campus.test", "ADMIN_PASSWORD": "Secret123"}
        with patch.dict(os.environ, env):
            self.assertTrue(ensure_default_admin(self.db_path))
            self.assertTrue(ensure_default_admin(self.db_path))  # second run changes nothing
        rows = self.rows("SELECT email, role, password_hash FROM users")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][:2], ("boss@campus.test", "admin"))
        self.assertTrue(check_password_hash(rows[0][2], "Secret123"))

    def test_default_admin_skipped_when_not_configured(self):
        init_db(self.db_path)
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(ensure_default_admin(self.db_path))
        self.assertEqual(self.rows("SELECT * FROM users"), [])

    def test_startup_does_not_crash_or_promote_when_admin_email_belongs_to_a_student(self):
        init_db(self.db_path)
        self.add_user("boss@campus.test", "student")
        env = {"ADMIN_EMAIL": "boss@campus.test", "ADMIN_PASSWORD": "Secret123"}
        with patch.dict(os.environ, env):
            with self.assertLogs("database", level="WARNING"):
                self.assertFalse(ensure_default_admin(self.db_path))
            create_app(testing=True, database_path=self.db_path, upload_folder=self.folder)  # must not raise
        self.assertEqual(self.rows("SELECT role FROM users"), [("student",)])

    def test_create_admin_user_creates_then_reports_existing(self):
        user_id, created = create_admin_user("new@campus.test", "Secret123", self.db_path)
        self.assertTrue(created)
        same_id, created_again = create_admin_user("NEW@campus.test", "Different1", self.db_path)
        self.assertEqual((same_id, created_again), (user_id, False))
        rows = self.rows("SELECT role, password_hash FROM users")
        self.assertEqual(len(rows), 1)
        self.assertTrue(check_password_hash(rows[0][1], "Secret123"))  # password not overwritten

    def test_create_admin_user_refuses_to_touch_a_student_account(self):
        init_db(self.db_path)
        self.add_user("kid@campus.test", "student")
        with self.assertRaises(ValueError):
            create_admin_user("kid@campus.test", "Secret123", self.db_path)
        self.assertEqual(self.rows("SELECT role FROM users"), [("student",)])


if __name__ == "__main__":
    unittest.main()
