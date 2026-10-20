"""Public pages, protected uploaded-image serving, and the health check."""
from flask import Blueprint, abort, current_app, render_template, send_from_directory

from database import get_db
from routes.auth_routes import get_logged_user, login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/uploads/<path:filename>")
@login_required
def serve_uploaded_file(filename):
    """Only the student who reported the issue, or an admin, may view its image."""
    user = get_logged_user()
    complaint = get_db().execute(
        "SELECT user_id FROM complaints WHERE image_filename = ?", (filename,)
    ).fetchone()
    # 404 (not 403) for both cases so filenames cannot be probed.
    if complaint is None or (user["role"] != "admin" and complaint["user_id"] != user["id"]):
        abort(404)
    response = send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@main_bp.route("/health")
def health_check():
    return {"status": "ok"}, 200
