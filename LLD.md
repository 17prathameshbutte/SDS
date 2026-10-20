# Low-Level Design (LLD)

## Pages and routes

### Public pages
- `/` — home page
- `/register` — student registration form
- `/login` — login page

### Student pages
- `/dashboard` — summary of student complaints
- `/report_issue` — complaint submission form
- `/my_tickets` — ticket list for the logged-in student
- `/issues` — shared list of unresolved issues with upvote/downvote controls
- `/issues/<id>/vote` — POST route to record, change, or remove a student's vote
- `/archive` — resolved tickets that have been resolved for at least one day
- `/ticket/<id>` — ticket detail page

### Admin pages
- `/admin` — all complaints with filters and search
- `/admin/update_status/<id>` — POST route for status changes

## Important functions

- `create_app()` (`app.py`) — configure the Flask application, set up the database and CSRF protection, register the blueprints
- `init_db()` (`database.py`) — create tables if missing
- `ensure_default_admin()` (`database.py`) — create the configured admin if environment values exist
- `login_required()` (`routes/auth_routes.py`) — check that a user is logged in (and still exists)
- `role_required()` (`routes/auth_routes.py`) — check access permissions by user role
- `read_valid_image()` (`routes/issue_routes.py`) — check an uploaded image's type, size, and real content
- `ticket_ref()` (`database.py`) — create a readable ticket ID like `CF-00001`
- `get_ticket_ai_suggestions()` — call Gemini and validate the response
- `vote_for_issue()` — store one student's vote per issue

## Database tables

### `users`
- `id`
- `name`
- `email`
- `password_hash`
- `role`
- `created_at`

### `complaints`
- `id`
- `user_id`
- `title`
- `category`
- `location`
- `description`
- `image_filename`
- `status`
- `ai_category`
- `ai_priority`
- `ai_explanation`
- `created_at`
- `updated_at`

### `status_history`
- `id`
- `complaint_id`
- `previous_status`
- `new_status`
- `changed_by`
- `changed_at`

### `complaint_votes`
- `id`
- `complaint_id`
- `user_id`
- `vote` (`1` for upvote, `-1` for downvote)
- `created_at`

## Validation rules

- Student registration requires full name, email, password, and confirm password.
- Complaint submission requires title, category, location, description, and image.
- File upload only accepts JPG and PNG files.
- Admin-only routes are checked on the server, not only in the UI.
- Students cannot view tickets that belong to other users.
- Each student has at most one vote per issue and can change or remove it.
- Resolved complaints older than one day appear in the archive and remain stored.

## AI priority levels

Gemini suggests Critical, Important, Normal, or Low. These are recommendations only; an administrator reviews the real-world issue.

## Gemini integration

The Gemini service is separated into `services/gemini_service.py` to keep AI logic distinct from route logic. It validates missing API keys and invalid JSON before saving AI output.
