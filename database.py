"""Database helpers for CampusFix: connections, schema setup and admin bootstrap."""
import logging
import os
import sqlite3

from flask import current_app, g
from werkzeug.security import generate_password_hash

from config import DATABASE

logger = logging.getLogger(__name__)

# Resolved tickets stay in normal lists for one day, then appear only in the archive.
ACTIVE_TICKET_SQL = "(status != 'Resolved' OR updated_at > datetime('now', '-1 day'))"


def ticket_ref(ticket_id):
    """Readable ticket ID such as CF-00001."""
    return f"CF-{ticket_id:05d}"


def get_db():
    """Return the SQLite connection for the current request (opened on first use)."""
    db = getattr(g, "_database", None)
    if db is None:
        db = sqlite3.connect(current_app.config["DATABASE"])
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")  # SQLite ignores foreign keys unless asked
        g._database = db
    return db


def close_db(_error=None):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()
        g._database = None


def init_db(db_path):
    """Create tables if they do not exist yet."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            image_filename TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            ai_category TEXT,
            ai_priority TEXT,
            ai_explanation TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            previous_status TEXT,
            new_status TEXT NOT NULL,
            changed_by INTEGER,
            changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id),
            FOREIGN KEY (changed_by) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS complaint_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            vote INTEGER NOT NULL CHECK (vote IN (-1, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (complaint_id, user_id),
            FOREIGN KEY (complaint_id) REFERENCES complaints(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )
    # One-time rename of the old priority labels to the current ones.
    conn.execute(
        """
        UPDATE complaints
        SET ai_priority = CASE ai_priority
            WHEN 'Urgent' THEN 'Critical'
            WHEN 'High' THEN 'Important'
            WHEN 'Medium' THEN 'Normal'
            ELSE ai_priority
        END
        """
    )
    conn.commit()
    conn.close()


def ensure_default_admin(db_path):
    """Create the admin from ADMIN_EMAIL / ADMIN_PASSWORD if both are set."""
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        return False
    conn = sqlite3.connect(db_path)
    try:
        existing = conn.execute(
            "SELECT id, role FROM users WHERE email = ?",
            (admin_email.lower(),),
        ).fetchone()
        if existing is not None and existing[1] != "admin":
            # Never silently promote a student account, and never crash the app at startup.
            logger.warning(
                "ADMIN_EMAIL %s is already registered as a %s account; no admin was created.",
                admin_email,
                existing[1],
            )
            return False
        if existing is None:
            conn.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
                (
                    "CampusFix Admin",
                    admin_email.lower(),
                    generate_password_hash(admin_password),
                ),
            )
            conn.commit()
        return True
    finally:
        conn.close()


def create_admin_user(email, password, db_path=DATABASE):
    """Create an admin account (used by `python app.py --create-admin`).

    Returns (user_id, created). Raises ValueError if the email already belongs to a non-admin.
    """
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        user = conn.execute(
            "SELECT id, role FROM users WHERE email = ?", (email.lower(),)
        ).fetchone()
        if user is not None:
            if user[1] != "admin":
                raise ValueError(f"{email} is already registered as a {user[1]} account; nothing was changed.")
            return user[0], False
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
            ("CampusFix Admin", email.lower(), generate_password_hash(password)),
        )
        conn.commit()
        return cursor.lastrowid, True
    finally:
        conn.close()


def init_app(app):
    """Hook the database into the Flask app: close connections, create tables, seed admin."""
    app.teardown_appcontext(close_db)
    init_db(app.config["DATABASE"])
    ensure_default_admin(app.config["DATABASE"])
