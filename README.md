# CampusFix

CampusFix is a beginner-friendly Flask web application for reporting and tracking campus infrastructure issues. Students can submit problems such as broken furniture, electrical faults, plumbing issues, or civil damage. Administrators can review complaints, filter them, and update statuses. The app also includes a small Gemini-based feature to suggest category and priority.

## Problem statement

Universities need a simple way to capture facilities issues before they become bigger problems. Traditional methods often lose complaints or make it difficult to track what happens next. CampusFix centralizes issue reporting and makes progress visible to both students and administrators.

## Features

- Student registration and secure login
- Password hashing using Werkzeug
- Complaint submission with image upload
- Ticket tracking by ID and status
- Issue board with one upvote or downvote per student
- Resolved tickets move to an archive view after one day and remain stored
- Administrator dashboard with filters and search
- Status history tracking
- AI suggestion for category and priority (when configured), including Cleaning and Other
- Categories: Electrical, Plumbing, Furniture, Civil, Cleaning, Other
- AI priority levels: Critical, Important, Normal, Low
- SQLite persistence for users and complaints
- Beginner-friendly documentation and testing

## Tech stack

- Python
- Flask
- SQLite
- HTML, CSS, Bootstrap 5, Jinja2
- JavaScript for small interface enhancements
- Google Gemini API via the official `google-genai` SDK
- Python `dotenv` for environment configuration

## Why this stack was selected

This combination is simple, open-source, and easy to explain in an interview. Flask is easy for beginners to understand, SQLite is lightweight and local, and Bootstrap helps build a professional-looking interface without a frontend build step.

## Folder structure

- `app.py` — main Flask application
- `config.py` — configuration values
- `requirements.txt` — Python dependencies
- `templates/` — HTML pages
- `static/` — CSS and JavaScript assets
- `services/gemini_service.py` — Gemini AI integration
- `tests/` — automated tests
- `docs/` — design and architecture notes
- `steering/` — project context and coding guidance

## Prerequisites

- Python 3.11+
- Windows PowerShell or VS Code terminal
- Internet access for Gemini API use (optional)

## Windows installation

```powershell
cd C:\Users\Pravin\Desktop\SDS
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Environment configuration

Create a local `.env` file using the example file:

```powershell
Copy-Item .env.example .env
```

Then update `.env`:

```env
SECRET_KEY=your-secret-key-here
GEMINI_API_KEY=your-gemini-api-key-here
ADMIN_EMAIL=admin@campusfix.local
ADMIN_PASSWORD=ChangeMe123!
```

## Create the first administrator

Use the built-in CLI helper:

```powershell
python app.py --create-admin --email admin@campusfix.local --password ChangeMe123!
```

## Run the application

```powershell
python app.py
```

Then open the browser to:

```text
http://127.0.0.1:5000/
```

## Run the tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

## Gemini API setup

1. Create a Google AI Studio account or use a valid Gemini API key.
2. Add the key to the `.env` file as `GEMINI_API_KEY`.
3. Restart the Flask app.
4. If the key is missing or the API fails, the complaint workflow still continues without AI suggestions.

## How to use the app

### Student

1. Open the home page.
2. Register a student account.
3. Log in and click "Report a New Issue".
4. Add the issue details, upload a JPG or PNG photo, and submit.
5. Use the dashboard or my tickets page to track each complaint.
6. Use Campus Issues to upvote or downvote open campus problems. You may change or remove your vote.
7. View tickets resolved for over one day from Archive; they are hidden from regular ticket lists, not deleted.

### Administrator

1. Log in with the admin email and password.
2. Open the admin dashboard.
3. Search, filter, and update statuses.
4. Review ticket history and AI guidance.

## Limitations

- This is a prototype for learning and interview preparation.
- It is not production ready for public internet deployment.
- Real deployment would require stronger security, backups, and production hosting.

## Security notes

- Passwords are hashed before storage.
- The app uses environment variables for secrets.
- Uploaded files are stored locally in the `uploads/` folder.
- The app protects admin routes and restricts unauthorized access.

## Future improvements

- More robust file validation
- Better duplicate detection
- Admin audit logs
- Role-based UI controls
- Notification workflow
