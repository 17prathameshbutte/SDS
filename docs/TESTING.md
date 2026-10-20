# Testing Notes

The project uses Python's built-in `unittest` framework and Flask's test client.

## What is tested

- page loading
- registration and duplicate email checks
- login success and failure
- complaint submission and validation
- unauthorized access rules
- vote creation, change, and removal
- archive timing after resolution
- admin status updates
- Gemini failure handling and the AI request timeout
- every template link (`url_for`) points to a real route, and every page renders
- admin search by ticket ID (`CF-00001`)
- sessions of deleted users, and login-protected image access
- CSRF protection on every form (these tests switch CSRF on)
- image content, size, and dimension checks
- foreign keys, admin account setup, and secret key handling
- admin navigation hides student-only links

Tests use temporary databases and upload folders, so running them never changes your real data or `uploads/` folder.

## Example command

```powershell
cd path\to\your\project-folder
.\.venv\Scripts\python -m unittest discover -s tests -v
```
