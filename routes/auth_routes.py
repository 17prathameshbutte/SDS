"""Registration, login, logout, and the login/role decorators used by every other route file."""
from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db

auth_bp = Blueprint("auth", __name__)


def get_logged_user():
    """Return the logged-in user's row, or None. Looked up once per request."""
    if "current_user" not in g:
        g.current_user = None
        user_id = session.get("user_id")
        if user_id:
            g.current_user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return g.current_user


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        # Also catches sessions whose user no longer exists in the database.
        if get_logged_user() is None:
            session.clear()
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)

    return wrapped


def role_required(role_name):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user = get_logged_user()
            if user is None:
                flash("Please log in to continue.", "error")
                return redirect(url_for("auth.login"))
            if user["role"] != role_name:
                flash("You are not allowed to access that page.", "error")
                if user["role"] == "admin":
                    return redirect(url_for("admin.admin_dashboard"))
                return redirect(url_for("student.student_dashboard"))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


@auth_bp.route("/register", methods=["GET", "POST"])
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
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session.clear()  # start from a clean session when logging in
        session["user_id"] = user["id"]
        session["user_role"] = user["role"]
        flash("Login successful.", "success")

        if user["role"] == "admin":
            return redirect(url_for("admin.admin_dashboard"))
        return redirect(url_for("student.student_dashboard"))

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("main.index"))
