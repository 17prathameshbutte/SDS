"""Administrator dashboard and status updates."""
import re

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from config import AI_PRIORITY_CHOICES, ALLOWED_STATUSES, CATEGORY_CHOICES
from database import ACTIVE_TICKET_SQL, get_db, ticket_ref
from routes.auth_routes import login_required, role_required

admin_bp = Blueprint("admin", __name__)


def ticket_number_from_search(text):
    """Turn 'CF-00012', 'cf12', '00012' or '12' into 12; return None for ordinary text."""
    match = re.fullmatch(r"(?:cf-?)?(\d{1,18})", text.strip(), re.IGNORECASE)
    return int(match.group(1)) if match else None


@admin_bp.route("/admin")
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
        search_sql = "LOWER(c.title) LIKE ? OR LOWER(c.location) LIKE ?"
        params.extend([term, term])
        ticket_number = ticket_number_from_search(search_term)
        if ticket_number is not None:
            search_sql += " OR c.id = ?"
            params.append(ticket_number)
        query += f" AND ({search_sql})"

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


@admin_bp.route("/admin/update_status/<int:ticket_id>", methods=["POST"])
@login_required
@role_required("admin")
def update_status(ticket_id):
    status = request.form.get("status")
    if status not in ALLOWED_STATUSES:
        flash("Invalid status selected.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    conn = get_db()
    complaint = conn.execute("SELECT * FROM complaints WHERE id = ?", (ticket_id,)).fetchone()
    if complaint is None:
        flash("Complaint not found.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    previous_status = complaint["status"]
    if previous_status == status:
        flash("Complaint already has that status.", "info")
        return redirect(url_for("admin.admin_dashboard"))

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
    return redirect(url_for("admin.admin_dashboard"))
