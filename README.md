Domain 2: WEBSITE DEVELOPMENT
Problem Statement Web 2:Smart Campus Issue Management Portal

**Architecture flow:**

+-------------------+
|   Frontend Layer  |
+-------------------+
| Student Portal    |
| Admin Dashboard   |
| HTML / CSS / JS   |
| Chart.js (UI)     |
+-------------------+
          |
          v
+-------------------+
|     AI Layer      |
+-------------------+
| Gemini API        |
| Categorization    |
| Priority, Dept    |
+-------------------+
          |
          v
+-------------------+
|   Database Layer  |
+-------------------+
| Firebase Firestore|
| Issues, Users     |
| Notifications     |
| Feedback          |
+-------------------+
          |
          v
+-------------------+
| Analytics Layer   |
+-------------------+
| Chart.js          |
| Visual Reports    |
| SLA & Satisfaction|
+-------------------+


**Working flow**:

1.Student submits issue → Title, description, location, category, priority, optional image

2.Flask server calls Gemini API → AI generates category, department, summary, confidence

3.If Gemini unavailable → Keyword fallback engine runs

4.Duplicate check → Warns if similar issue already exists

5.Issue stored in Firestore → With SLA deadlines (Critical 2h, High 4h, Medium 8h, Low 24h)

6.Admin dashboard → Search, filter, assign to department/staff, track lifecycle (Pending → Assigned → In Progress → Resolved → Reopened)

7.Notifications → Students and admins get in-app alerts for submissions, assignments, resolutions

8.Feedback loop → Student rates resolution (1–5 stars + comments)

9.Analytics → Chart.js visualizes categories, priorities, overdue issues, resolution times, satisfaction trends.

**Technical Stack:**

Frontend (HTML → CSS → JavaScript → Chart.js)
        ↓
Backend (Python → Flask → REST API → SLA Logic)
        ↓
AI Layer (Gemini API → Fallback Keyword Engine)
        ↓
Database (Firebase Firestore → Collections: issues, users, notifications, feedback)
        ↓
Analytics (Chart.js → Visualization → Insights)

Team Name :**RAVEN**

**Team Members:**

Suruthi PR
Vanisha S
Saranya M
Vignesh Rahul E

College Name: Dr.N.G.P. Institute of Technology



