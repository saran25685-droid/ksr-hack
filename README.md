# CampusFix AI

**Report. Resolve. Improve.**

CampusFix AI is a Flask-based smart campus issue portal. Students submit campus problems in plain language, receive explainable AI recommendations, and follow the issue through assignment, SLA tracking, resolution, and feedback. Admins get a compact operations dashboard for triage, assignment, status changes, analytics, and satisfaction trends.

## What is included

- Student and Admin demo login
- Student issue reporting with title, description, location, room, category, priority, and optional image URL
- Server-side Gemini analysis for category, priority, department, summary, reason, and confidence
- Deterministic keyword fallback when Gemini is unavailable, so the demo never blocks
- Similar complaint warning before/while submitting, with issue ID and status
- Admin search and filters by title, ID, student, location, category, priority, status, and department
- Assignment to department and staff; lifecycle: Pending, Assigned, In Progress, Resolved, Reopened
- SLA targets: Critical 2 hours, High 4 hours, Medium 8 hours, Low 24 hours
- In-app notifications for submissions, assignments, and resolutions
- Student 1-5 star feedback and comments after resolution
- Chart.js analytics for category, priority, status, department, overdue issues, resolution time, and satisfaction
- Seeded issues for Wi-Fi, projector, water leakage, fan, cleanliness, electrical, and lab equipment examples

## Run locally

```powershell
cd c:\Users\saran\OneDrive\Desktop\ksr
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open http://127.0.0.1:5000.

Demo accounts:

- Student: `student@campus.com` / `student123`
- Admin: `admin@campus.com` / `admin123`

## Gemini and Firestore setup

The real API key is never placed in browser JavaScript. Put `GEMINI_API_KEY` in `.env`; the Flask server calls Gemini and accepts only valid structured values. If the API is unavailable, the local recommendation engine is used.

For Firestore, create a Firebase service account, set `GOOGLE_APPLICATION_CREDENTIALS` to its local JSON path, and restart Flask. The app writes issue documents to `issues` and notification documents to `notifications`. The local in-memory seed remains available for a no-credentials presentation.

## Architecture

`app.py` owns the small Flask API, session authentication, fallback AI rules, duplicate similarity, SLA calculations, and optional Firestore writes. `templates/index.html` is the single application shell. `static/app.js` renders Student and Admin views and calls the API. `static/styles.css` provides the responsive visual system. This keeps the project easy to explain and avoids a build step.

## Firestore document shape

The `issues` document includes `id`, `student_email`, `student_name`, `title`, `description`, `location`, `room`, `category`, `priority`, all `ai_*` recommendation fields, `assigned_department`, `assigned_staff`, `status`, timestamps, `due_at`, `overdue` (calculated), `resolved_at`, feedback fields, and optional `image`.

The other intended collections are `users`, `notifications`, and `feedback`. Demo users are kept in the local store so the app can be started in minutes; production authentication should replace this with Firebase Auth.

## Quick verification

```powershell
python -m py_compile app.py
```

The complete automated smoke path is covered by the Flask test client: login, AI analysis, student submission, admin resolution, and student feedback. For the live demo, use Student demo -> Report an issue -> Analyze with AI -> Submit, then sign out and use Admin demo to assign and resolve the new issue.

## Future improvements

Use Firebase Auth, upload images to Cloud Storage, load Firestore documents on startup, add role-based custom claims, and introduce a background scheduler for SLA escalation. Those are intentionally outside the 4-hour prototype scope.