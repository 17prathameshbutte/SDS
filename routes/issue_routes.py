"""Reporting issues, the campus issue board with voting, the archive, and ticket details."""
import io
import os
import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from PIL import Image

from config import ALLOWED_EXTENSIONS, CATEGORY_CHOICES
from database import get_db, ticket_ref
from routes.auth_routes import get_logged_user, login_required, role_required
from services.gemini_service import get_ticket_ai_suggestions

issues_bp = Blueprint("issues", __name__)

# Image formats we accept, as reported by Pillow after reading the file itself.
IMAGE_FORMAT_EXTENSIONS = {"PNG": "png", "JPEG": "jpg"}


def read_valid_image(file):
    """Check an uploaded image and return (bytes, extension) to store.

    The extension, size and real content are all checked. The stored extension comes from
    the detected image format, never from the name the user typed. Raises ValueError with a
    message that is safe to show to the user.
    """
    name = file.filename or ""
    extension = name.rsplit(".", 1)[1].lower() if "." in name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Only JPG and PNG image files are allowed.")

    max_bytes = current_app.config["MAX_IMAGE_BYTES"]
    data = file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"Image is too large. The maximum size is {max_bytes / (1024 * 1024):g} MB.")

    not_an_image = "The uploaded file is not a valid JPG or PNG image."
    try:
        image = Image.open(io.BytesIO(data))
        detected_format = image.format
        width, height = image.size
    except Exception:
        raise ValueError(not_an_image)

    if detected_format not in IMAGE_FORMAT_EXTENSIONS:
        raise ValueError("Only JPG and PNG image files are allowed.")
    if width * height > current_app.config["MAX_IMAGE_PIXELS"]:
        raise ValueError("Image dimensions are too large. Please upload a smaller image.")
    try:
        image.verify()  # detects truncated or corrupt files
    except Exception:
        raise ValueError(not_an_image)

    return data, IMAGE_FORMAT_EXTENSIONS[detected_format]


@issues_bp.route("/report_issue", methods=["GET", "POST"])
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

        try:
            image_bytes, extension = read_valid_image(file)
        except ValueError as error:
            flash(str(error), "error")
            return render_template("report_issue.html", categories=CATEGORY_CHOICES)

        unique_name = f"{uuid.uuid4().hex}.{extension}"
        file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name)
        with open(file_path, "wb") as image_file:
            image_file.write(image_bytes)

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
        return redirect(url_for("student.my_tickets"))

    return render_template("report_issue.html", categories=CATEGORY_CHOICES)


@issues_bp.route("/issues")
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


@issues_bp.route("/issues/<int:ticket_id>/vote", methods=["POST"])
@login_required
@role_required("student")
def vote_for_issue(ticket_id):
    vote = request.form.get("vote")
    if vote not in {"1", "-1"}:
        flash("Please choose an upvote or downvote.", "error")
        return redirect(url_for("issues.issue_board"))

    conn = get_db()
    complaint = conn.execute(
        "SELECT id, status FROM complaints WHERE id = ?",
        (ticket_id,),
    ).fetchone()
    if complaint is None or complaint["status"] == "Resolved":
        flash("This issue is no longer open for voting.", "error")
        return redirect(url_for("issues.issue_board"))

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
    return redirect(url_for("issues.issue_board"))


@issues_bp.route("/archive")
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


@issues_bp.route("/ticket/<int:ticket_id>")
@login_required
def ticket_detail(ticket_id):
    user = get_logged_user()
    conn = get_db()
    complaint = conn.execute("SELECT * FROM complaints WHERE id = ?", (ticket_id,)).fetchone()
    if complaint is None:
        flash("Ticket not found.", "error")
        if user["role"] == "admin":
            return redirect(url_for("admin.admin_dashboard"))
        return redirect(url_for("student.my_tickets"))
    if user["role"] != "admin" and complaint["user_id"] != user["id"]:
        flash("You cannot view another student's ticket.", "error")
        return redirect(url_for("student.my_tickets"))

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
