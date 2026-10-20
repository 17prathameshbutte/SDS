"""Student dashboard and "my tickets" list."""
from flask import Blueprint, redirect, render_template, url_for

from database import ACTIVE_TICKET_SQL, get_db, ticket_ref
from routes.auth_routes import get_logged_user, login_required

student_bp = Blueprint("student", __name__)


@student_bp.route("/dashboard")
@login_required
def student_dashboard():
    user = get_logged_user()
    if user is None:
        return redirect(url_for("auth.login"))
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


@student_bp.route("/my_tickets")
@login_required
def my_tickets():
    user = get_logged_user()
    if user is None:
        return redirect(url_for("auth.login"))
    conn = get_db()
    complaints = conn.execute(
        f"SELECT * FROM complaints WHERE user_id = ? AND {ACTIVE_TICKET_SQL} ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    return render_template("my_tickets.html", complaints=complaints, ticket_ref=ticket_ref)
