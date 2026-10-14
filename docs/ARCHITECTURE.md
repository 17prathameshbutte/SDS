# Architecture Notes

CampusFix uses a simple layered structure:

- Presentation layer: HTML templates with Bootstrap styling
- Application layer: Flask routes and validation logic
- Data layer: SQLite database with `users`, `complaints`, and `status_history`
- AI layer: optional Gemini-based recommendations

This is intentionally simple so a beginner can understand every major part without needing a large framework or complex deployment pattern.
