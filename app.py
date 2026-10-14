import argparse
import os
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import ALLOWED_EXTENSIONS, DATABASE, MAX_CONTENT_LENGTH, SECRET_KEY, UPLOAD_FOLDER
from services.gemini_service import get_ticket_ai_suggestions

ALLOWED_STATUSES = ["Pending", "In Progress", "Resolved"]
CATEGORY_CHOICES = ["Electrical", "Plumbing", "Furniture", "Civil", "Cleaning", "Other"]
AI_PRIORITY_CHOICES = ["Critical", "Important", "Normal", "Low"]
ACTIVE_TICKET_SQL = "(status != 'Resolved' OR updated_at > datetime('now', '-1 day'))"


def create_app(testing=False, database_path=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["TESTING"] = testing
    app.config["DATABASE"] = database_path or DATABASE

    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    def get_db():
        db = getattr(g, "_database", None)
        if db is None:
            db = sqlite3.connect(app.config["DATABASE"])
            db.row_factory = sqlite3.Row
            g._database = db
        return db

    def close_db(_error=None):
        db = getattr(g, "_database", None)
        if db is not None:
            db.close()
            g._database = None

    def init_db():
        conn = sqlite3.connect(app.config["DATABASE"])
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

    def ensure_default_admin():
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_email or not admin_password:
            return False
        conn = sqlite3.connect(app.config["DATABASE"])
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ? AND role = 'admin'",
            (admin_email.lower(),),
        ).fetchone()
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
        conn.close()
        return True

    def ticket_ref(ticket_id):
        return f"CF-{ticket_id:05d}"

    def get_logged_user():
        user_id = session.get("user_id")
        if not user_id:
            return None
        conn = get_db()
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def login_required(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            return view_func(*args, **kwargs)

        return wrapped

    def role_required(role_name):
        def decorator(view_func):
            @wraps(view_func)
            def wrapped(*args, **kwargs):
                user = get_logged_user()
                if user is None:
                    flash("Please log in to continue.", "error")
                    return redirect(url_for("login"))
                if user["role"] != role_name:
                    flash("You are not allowed to access that page.", "error")
                    if user["role"] == "admin":
                        return redirect(url_for("admin_dashboard"))
                    return redirect(url_for("student_dashboard"))
                return view_func(*args, **kwargs)

            return wrapped

        return decorator

    @app.teardown_appcontext
    def teardown(_exception):
        close_db()

    with app.app_context():
        init_db()
        ensure_default_admin()

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            confirm_password = request.form.get("confirm_password") or ""

            if not name or not email or not password:
                flash("All fields are required.", "error")
                return render_template("register.html")
            if password != confirm_password:
                flash("Passwords do not match.", "error")
                return render_template("register.html")
            if len(password) < 6:
                flash("Password must be at least 6 characters long.", "error")
                return render_template("register.html")

            conn = get_db()
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                flash("An account with this email already exists.", "error")
                return render_template("register.html")

            conn.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'student')",
                (name, email, generate_password_hash(password)),
            )
            conn.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""

            conn = get_db()
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Invalid email or password.", "error")
                return render_template("login.html")

            session["user_id"] = user["id"]
            session["user_role"] = user["role"]
            flash("Login successful.", "success")

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("student_dashboard"))

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("index"))

    @app.route("/dashboard")
    @login_required
    def student_dashboard():
        user = get_logged_user()
        if user is None:
            return redirect(url_for("login"))
        conn = get_db()
        complaints = conn.execute(
            f"""
            SELECT * FROM complaints
            WHERE user_id = ? AND {ACTIVE_TICKET_SQL}
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (user["id"],),
        ).fetchall()
        stats = {
            "pending": conn.execute(
                f"SELECT COUNT(*) as count FROM complaints WHERE user_id = ? AND status = 'Pending' AND {ACTIVE_TICKET_SQL}",
                (user["id"],),
            ).fetchone()["count"],
            "progress": conn.execute(
                f"SELECT COUNT(*) as count FROM complaints WHERE user_id = ? AND status = 'In Progress' AND {ACTIVE_TICKET_SQL}",
                (user["id"],),
            ).fetchone()["count"],
            "resolved": conn.execute(
                f"SELECT COUNT(*) as count FROM complaints WHERE user_id = ? AND status = 'Resolved' AND {ACTIVE_TICKET_SQL}",
                (user["id"],),
            ).fetchone()["count"],
        }
        return render_template(
            "student_dashboard.html",
            complaints=complaints,
            user=user,
            stats=stats,
            ticket_ref=ticket_ref,
        )

    @app.route("/report_issue", methods=["GET", "POST"])
    @login_required
    def report_issue():
        user = get_logged_user()
        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            category = (request.form.get("category") or "").strip()
            location = (request.form.get("location") or "").strip()
            description = (request.form.get("description") or "").strip()
            file = request.files.get("image")

            is_valid = bool(title) and bool(category) and bool(location) and bool(description)
            if not is_valid:
                flash("Please fill in all required fields.", "error")
                return render_template("report_issue.html", categories=CATEGORY_CHOICES)

            if category not in CATEGORY_CHOICES:
                flash("Please select a valid category.", "error")
                return render_template("report_issue.html", categories=CATEGORY_CHOICES)

            if file is None or file.filename == "":
                flash("Please upload an image for the complaint.", "error")
                return render_template("report_issue.html", categories=CATEGORY_CHOICES)

            extension = file.filename.rsplit(".", 1)[1].lower() if "." in file.filename else ""
            if extension not in ALLOWED_EXTENSIONS:
                flash("Only JPG and PNG image files are allowed.", "error")
                return render_template("report_issue.html", categories=CATEGORY_CHOICES)

            filename = secure_filename(file.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
            file.save(file_path)

            ai_result = get_ticket_ai_suggestions(title, description, category)
            ai_category = ai_result.get("category") if ai_result.get("status") == "ok" else None
            ai_priority = ai_result.get("priority") if ai_result.get("status") == "ok" else None
            ai_explanation = ai_result.get("explanation") if ai_result.get("status") == "ok" else ai_result.get("explanation", "AI suggestion unavailable.")

            conn = get_db()
            cursor = conn.execute(
                """
                INSERT INTO complaints (
                    user_id, title, category, location, description, image_filename,
                    ai_category, ai_priority, ai_explanation, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', CURRENT_TIMESTAMP)
                """,
                (
                    user["id"],
                    title,
                    category,
                    location,
                    description,
                    unique_name,
                    ai_category,
                    ai_priority,
                    ai_explanation,
                ),
            )
            conn.commit()
            complaint_id = cursor.lastrowid

            conn.execute(
                "INSERT INTO status_history (complaint_id, previous_status, new_status, changed_by) VALUES (?, ?, ?, ?)",
                (complaint_id, "New", "Pending", user["id"]),
            )
            conn.commit()

            flash(f"Complaint submitted successfully. Ticket ID: {ticket_ref(complaint_id)}", "success")
            return redirect(url_for("my_tickets"))

        return render_template("report_issue.html", categories=CATEGORY_CHOICES)

    @app.route("/my_tickets")
    @login_required
    def my_tickets():
        user = get_logged_user()
        if user is None:
            return redirect(url_for("login"))
        conn = get_db()
        complaints = conn.execute(
            f"SELECT * FROM complaints WHERE user_id = ? AND {ACTIVE_TICKET_SQL} ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
        return render_template("my_tickets.html", complaints=complaints, ticket_ref=ticket_ref)

    @app.route("/issues")
    @login_required
    def issue_board():
        conn = get_db()
        complaints = conn.execute(
            """
            SELECT c.*,
                (SELECT COUNT(*) FROM complaint_votes v WHERE v.complaint_id = c.id AND v.vote = 1) AS upvotes,
                (SELECT COUNT(*) FROM complaint_votes v WHERE v.complaint_id = c.id AND v.vote = -1) AS downvotes,
                (SELECT v.vote FROM complaint_votes v WHERE v.complaint_id = c.id AND v.user_id = ?) AS my_vote
            FROM complaints c
            WHERE c.status != 'Resolved'
            ORDER BY (upvotes - downvotes) DESC, c.created_at DESC
            """,
            (session["user_id"],),
        ).fetchall()
        return render_template(
            "issue_board.html",
            complaints=complaints,
            ticket_ref=ticket_ref,
        )

    @app.route("/issues/<int:ticket_id>/vote", methods=["POST"])
    @login_required
    @role_required("student")
    def vote_for_issue(ticket_id):
        vote = request.form.get("vote")
        if vote not in {"1", "-1"}:
            flash("Please choose an upvote or downvote.", "error")
            return redirect(url_for("issue_board"))

        conn = get_db()
        complaint = conn.execute(
            "SELECT id, status FROM complaints WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        if complaint is None or complaint["status"] == "Resolved":
            flash("This issue is no longer open for voting.", "error")
            return redirect(url_for("issue_board"))

        current_vote = conn.execute(
            "SELECT vote FROM complaint_votes WHERE complaint_id = ? AND user_id = ?",
            (ticket_id, session["user_id"]),
        ).fetchone()
        vote_value = int(vote)
        if current_vote is not None and current_vote["vote"] == vote_value:
            conn.execute(
                "DELETE FROM complaint_votes WHERE complaint_id = ? AND user_id = ?",
                (ticket_id, session["user_id"]),
            )
            flash("Your vote was removed.", "success")
        elif current_vote is None:
            conn.execute(
                "INSERT INTO complaint_votes (complaint_id, user_id, vote) VALUES (?, ?, ?)",
                (ticket_id, session["user_id"], vote_value),
            )
            flash("Your vote was recorded.", "success")
        else:
            conn.execute(
                """
                UPDATE complaint_votes
                SET vote = ?, created_at = CURRENT_TIMESTAMP
                WHERE complaint_id = ? AND user_id = ?
                """,
                (vote_value, ticket_id, session["user_id"]),
            )
            flash("Your vote was changed.", "success")
        conn.commit()
        return redirect(url_for("issue_board"))

    @app.route("/archive")
    @login_required
    def archived_tickets():
        user = get_logged_user()
        conn = get_db()
        if user["role"] == "admin":
            complaints = conn.execute(
                """
                SELECT * FROM complaints
                WHERE status = 'Resolved' AND updated_at <= datetime('now', '-1 day')
                ORDER BY updated_at DESC
                """
            ).fetchall()
        else:
            complaints = conn.execute(
                """
                SELECT * FROM complaints
                WHERE user_id = ? AND status = 'Resolved'
                    AND updated_at <= datetime('now', '-1 day')
                ORDER BY updated_at DESC
                """,
                (user["id"],),
            ).fetchall()
        return render_template(
            "archive.html",
            complaints=complaints,
            ticket_ref=ticket_ref,
        )

    @app.route("/ticket/<int:ticket_id>")
    @login_required
    def ticket_detail(ticket_id):
        user = get_logged_user()
        conn = get_db()
        complaint = conn.execute("SELECT * FROM complaints WHERE id = ?", (ticket_id,)).fetchone()
        if complaint is None:
            flash("Ticket not found.", "error")
            return redirect(url_for("my_tickets"))
        if user["role"] != "admin" and complaint["user_id"] != user["id"]:
            flash("You cannot view another student's ticket.", "error")
            return redirect(url_for("my_tickets"))

        history = conn.execute(
            """
            SELECT h.*, u.name as changed_by_name
            FROM status_history h
            LEFT JOIN users u ON h.changed_by = u.id
            WHERE h.complaint_id = ?
            ORDER BY h.changed_at DESC
            """,
            (ticket_id,),
        ).fetchall()
        return render_template(
            "ticket_detail.html",
            complaint=complaint,
            history=history,
            ticket_ref=ticket_ref,
        )

    @app.route("/admin")
    @login_required
    @role_required("admin")
    def admin_dashboard():
        conn = get_db()
        status_filter = request.args.get("status", "")
        category_filter = request.args.get("category", "")
        search_term = (request.args.get("search") or "").strip()

        query = f"""
            SELECT c.*,
                (SELECT COUNT(*) FROM complaint_votes v WHERE v.complaint_id = c.id AND v.vote = 1) AS upvotes,
                (SELECT COUNT(*) FROM complaint_votes v WHERE v.complaint_id = c.id AND v.vote = -1) AS downvotes
            FROM complaints c
            WHERE {ACTIVE_TICKET_SQL}
        """
        params = []

        if search_term:
            term = f"%{search_term.lower()}%"
            query += " AND (LOWER(c.title) LIKE ? OR CAST(c.id AS TEXT) LIKE ? OR LOWER('CF-' || CAST(c.id AS TEXT)) LIKE ? OR LOWER(c.location) LIKE ?)"
            params.extend([term, f"%{search_term}%", term, term])

        if status_filter:
            query += " AND c.status = ?"
            params.append(status_filter)
        if category_filter:
            query += " AND c.category = ?"
            params.append(category_filter)

        query += " ORDER BY c.created_at DESC"
        complaints = conn.execute(query, params).fetchall()

        stats = {
            "pending": conn.execute(f"SELECT COUNT(*) as count FROM complaints WHERE status = 'Pending' AND {ACTIVE_TICKET_SQL}").fetchone()["count"],
            "progress": conn.execute(f"SELECT COUNT(*) as count FROM complaints WHERE status = 'In Progress' AND {ACTIVE_TICKET_SQL}").fetchone()["count"],
            "resolved": conn.execute(f"SELECT COUNT(*) as count FROM complaints WHERE status = 'Resolved' AND {ACTIVE_TICKET_SQL}").fetchone()["count"],
            "total": conn.execute(f"SELECT COUNT(*) as count FROM complaints WHERE {ACTIVE_TICKET_SQL}").fetchone()["count"],
        }
        return render_template(
            "admin_dashboard.html",
            complaints=complaints,
            ticket_ref=ticket_ref,
            stats=stats,
            status_filter=status_filter,
            category_filter=category_filter,
            search_term=search_term,
            categories=CATEGORY_CHOICES,
            statuses=ALLOWED_STATUSES,
            priorities=AI_PRIORITY_CHOICES,
        )

    @app.route("/admin/update_status/<int:ticket_id>", methods=["POST"])
    @login_required
    @role_required("admin")
    def update_status(ticket_id):
        status = request.form.get("status")
        if status not in ALLOWED_STATUSES:
            flash("Invalid status selected.", "error")
            return redirect(url_for("admin_dashboard"))

        conn = get_db()
        complaint = conn.execute("SELECT * FROM complaints WHERE id = ?", (ticket_id,)).fetchone()
        if complaint is None:
            flash("Complaint not found.", "error")
            return redirect(url_for("admin_dashboard"))

        previous_status = complaint["status"]
        if previous_status == status:
            flash("Complaint already has that status.", "info")
            return redirect(url_for("admin_dashboard"))

        conn.execute(
            "UPDATE complaints SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, ticket_id),
        )
        conn.execute(
            "INSERT INTO status_history (complaint_id, previous_status, new_status, changed_by) VALUES (?, ?, ?, ?)",
            (ticket_id, previous_status, status, session["user_id"]),
        )
        conn.commit()
        flash(f"Status updated to {status}.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/uploads/<path:filename>")
    def serve_uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

    @app.route("/health")
    def health_check():
        return {"status": "ok"}, 200

    return app


def create_admin_user(email, password):
    app = create_app(testing=True)
    conn = sqlite3.connect(app.config["DATABASE"])
    user = conn.execute("SELECT id FROM users WHERE email = ?", (email.lower(),)).fetchone()
    if user:
        return user[0]
    conn.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
        ("CampusFix Admin", email.lower(), generate_password_hash(password)),
    )
    conn.commit()
    new_user = conn.execute("SELECT id FROM users WHERE email = ?", (email.lower(),)).fetchone()
    conn.close()
    return new_user[0] if new_user else None


def main():
    parser = argparse.ArgumentParser(description="Run CampusFix")
    parser.add_argument("--create-admin", action="store_true", help="Create the first admin account")
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--password", help="Admin password")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.create_admin:
        if not args.email or not args.password:
            raise SystemExit("Both --email and --password are required when creating an admin account.")
        admin_id = create_admin_user(args.email, args.password)
        if admin_id:
            print(f"Admin account created successfully for {args.email}.")
        else:
            print("Admin account could not be created.")
        return

    app = create_app(testing=False)
    app.run(debug=args.debug, host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
