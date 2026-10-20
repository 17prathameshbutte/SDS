"""CampusFix entry point: create and configure the Flask app, register blueprints, run the server."""
import argparse
import os

from flask import Flask, flash, redirect, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.exceptions import RequestEntityTooLarge

from config import (
    DATABASE,
    MAX_CONTENT_LENGTH,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    SECRET_KEY,
    SECRET_KEY_IS_RANDOM,
    UPLOAD_FOLDER,
)
from database import create_admin_user, init_app
from routes import register_blueprints

csrf = CSRFProtect()


def create_app(testing=False, database_path=None, upload_folder=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["UPLOAD_FOLDER"] = upload_folder or UPLOAD_FOLDER
    app.config["MAX_IMAGE_BYTES"] = MAX_IMAGE_BYTES
    app.config["MAX_IMAGE_PIXELS"] = MAX_IMAGE_PIXELS
    app.config["TESTING"] = testing
    app.config["DATABASE"] = database_path or DATABASE
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # CSRF tokens are checked on every POST. Tests switch this off unless they are testing CSRF itself.
    app.config["WTF_CSRF_ENABLED"] = not testing
    app.config["WTF_CSRF_TIME_LIMIT"] = None  # token stays valid for the whole browser session

    if SECRET_KEY_IS_RANDOM and not testing:
        print(
            "WARNING: SECRET_KEY is missing or still a placeholder. Using a temporary random key; "
            "users will be logged out whenever the app restarts. Set SECRET_KEY in your .env file."
        )

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    init_app(app)
    csrf.init_app(app)
    register_blueprints(app)

    @app.errorhandler(CSRFError)
    def csrf_failed(_error):
        flash("Your form session has expired or is invalid. Please try again.", "error")
        return redirect(url_for("main.index"))

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(_error):
        flash("That upload is too large. Please choose a smaller image.", "error")
        return redirect(url_for("issues.report_issue"))

    return app


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
        try:
            _admin_id, created = create_admin_user(args.email, args.password)
        except ValueError as error:
            raise SystemExit(str(error))
        if created:
            print(f"Admin account created successfully for {args.email}.")
        else:
            print(f"An admin account already exists for {args.email}; nothing was changed.")
        return

    app = create_app(testing=False)
    app.run(debug=args.debug, host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
