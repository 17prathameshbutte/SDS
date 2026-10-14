# Viva Preparation

Possible questions and answers:

1. What is Flask used for in this app?
   - Flask handles routes, form processing, sessions, and page rendering.

2. Why is SQLite used?
   - It is lightweight, local, and enough for a beginner project.

3. What is the purpose of `status_history`?
   - It stores every change in the complaint lifecycle.

4. Why is AI suggestions optional?
   - Because API keys may be missing or unavailable without breaking the app.

5. Why hash passwords?
   - So plain passwords are not stored in the database.

6. How does voting work?
   - The SQLite `complaint_votes` table stores one vote per student per issue. A student can change the vote or click the same choice to remove it.

7. Are archived tickets deleted?
   - No. A resolved ticket moves to the archive after one day but stays in SQLite for review.

8. What do AI priority levels mean?
   - Critical, Important, Normal, and Low are suggestions for an administrator to review, not a verified safety assessment.
