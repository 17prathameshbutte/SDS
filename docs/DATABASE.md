# Database Design

The application stores data locally using SQLite. The schema is intentionally small and easy to explain.

## Tables

### `users`
Stores account details and role information.

### `complaints`
Stores all submitted complaint records, including the ticket status and AI recommendation fields.

### `status_history`
Tracks each status change with timestamps and the administrator who made it.

### `complaint_votes`
Stores a student's upvote (`1`) or downvote (`-1`) for a complaint. A unique constraint on complaint and user makes each vote changeable but prevents duplicate votes.

## Relationship

Each complaint belongs to one student user. A complaint can have multiple status updates recorded in `status_history`.
Each vote belongs to one user and one complaint.

## Archive behavior

A resolved complaint is shown in ordinary lists for 24 hours after its last status update. It then appears in the archive. The record, votes, and photo are retained; nothing is automatically deleted.
