"""Blueprint registration for CampusFix."""


def register_blueprints(app):
    from routes.admin_routes import admin_bp
    from routes.auth_routes import auth_bp
    from routes.issue_routes import issues_bp
    from routes.main_routes import main_bp
    from routes.student_routes import student_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(issues_bp)
    app.register_blueprint(admin_bp)
