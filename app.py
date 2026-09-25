import json
import os
import re
import uuid
import urllib.request
import base64
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, jsonify, render_template, request, session

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google.cloud import firestore
except ImportError:
    firestore = None

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "campusfix-demo-secret")

SLA_HOURS = {"Critical": 2, "High": 4, "Medium": 8, "Low": 24}
CATEGORIES = ["Network", "Classroom Equipment", "Cleanliness", "Infrastructure", "Electrical", "Lab Equipment", "Other"]
DEPARTMENTS = ["IT Support", "Facilities", "Housekeeping", "Electrical Services", "Lab Operations"]
STAFF_NAMES = ["Arun Kumar", "Priya Sharma", "Karthik Raj"]
STAFF = {department: STAFF_NAMES for department in ("IT Support", "Facilities", "Housekeeping", "Electrical Services", "Lab Operations")}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def parse_dt(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def issue_view(issue):
    result = dict(issue)
    for key in ("created_at", "updated_at", "due_at", "resolved_at"):
        result[key] = iso(result.get(key))
    result["overdue"] = result["status"] != "Resolved" and now() > parse_dt(issue["due_at"])
    if result["status"] == "Resolved" and result.get("resolved_at"):
        result["resolution_hours"] = round((parse_dt(issue["resolved_at"]) - parse_dt(issue["created_at"])).total_seconds() / 3600, 1)
    else:
        result["resolution_hours"] = None
    result["update_history"] = [
        {**entry, "created_at": iso(entry["created_at"])}
        for entry in issue.get("update_history", [])
    ]
    return result


def activity(issue, event, message, user):
    issue.setdefault("update_history", []).append({
        "event": event,
        "message": message,
        "actor": user["name"],
        "role": user["role"],
        "created_at": now(),
    })


class Store:
    def __init__(self):
        self.firestore = None
        if firestore and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            try:
                self.firestore = firestore.Client()
            except Exception:
                self.firestore = None
        self.users = {
            "student@campus.com": {"email": "student@campus.com", "name": "Ananya Sharma", "role": "Student", "password": "student123"},
            "admin@campus.com": {"email": "admin@campus.com", "name": "Dr. Rahul Menon", "role": "Admin", "password": "admin123"},
        }
        self.issues = {}
        self.notifications = []
        self.feedback = []
        self.seed()
        self.load_firestore()

    def load_firestore(self):
        if not self.firestore:
            return
        try:
            for document in self.firestore.collection("users").stream():
                user = document.to_dict()
                if user.get("email"):
                    self.users[user["email"].lower()] = user
            for document in self.firestore.collection("issues").stream():
                self.issues[document.id] = document.to_dict()
            for document in self.firestore.collection("notifications").stream():
                notification = document.to_dict()
                notification["id"] = document.id
                self.notifications.append(notification)
            self.notifications.sort(key=lambda item: item.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        except Exception:
            pass

    def persist_user(self, user):
        if self.firestore:
            self.firestore.collection("users").document(user["email"].lower()).set(user)

    def seed(self):
        examples = [
            ("Wi-Fi failure in library", "Campus Wi-Fi has been unavailable on the second floor since morning.", "Central Library", "Network", "High", "IT Support", "In Progress", "student@campus.com"),
            ("Projector failure in CSE 204", "The projector is not displaying anything before a seminar.", "CSE Block Room 204", "Classroom Equipment", "Critical", "IT Support", "Assigned", "student@campus.com"),
            ("Water leakage near Block B", "Water is leaking from the ceiling near the stairwell.", "Block B, first floor", "Infrastructure", "High", "Facilities", "Pending", "student@campus.com"),
            ("Broken classroom fan", "The ceiling fan in the classroom makes a loud noise and stops.", "ECE Block Room 110", "Electrical", "Medium", "Electrical Services", "Resolved", "student@campus.com"),
            ("Unclean washroom", "Washroom needs cleaning and soap dispensers are empty.", "Main Building, ground floor", "Cleanliness", "Medium", "Housekeeping", "Resolved", "student@campus.com"),
            ("Lab computer not starting", "Computer 18 in the programming lab will not boot.", "IT Lab 2", "Lab Equipment", "High", "Lab Operations", "In Progress", "student@campus.com"),
        ]
        created = now() - timedelta(days=2)
        for index, item in enumerate(examples):
            title, description, location, category, priority, department, status, email = item
            issue_id = f"CF-{1024 + index}"
            created_at = created + timedelta(hours=index * 5)
            resolved_at = created_at + timedelta(hours=3) if status == "Resolved" else None
            self.issues[issue_id] = {"id": issue_id, "student_email": email, "student_name": self.users[email]["name"], "title": title, "description": description, "location": location, "room": location, "category": category, "priority": priority, "ai_category": category, "ai_priority": priority, "ai_department": department, "ai_summary": title, "ai_reason": "Seeded demo issue", "ai_confidence": 96, "assigned_department": department if status != "Pending" else "", "assigned_staff": STAFF.get(department, [""])[0] if status != "Pending" else "", "status": status, "created_at": created_at, "updated_at": created_at, "due_at": created_at + timedelta(hours=SLA_HOURS[priority]), "resolved_at": resolved_at, "feedback_rating": 4 if resolved_at else None, "feedback_comment": "Quick resolution, thank you!" if resolved_at else "", "update_history": [{"message": f"Issue created with status {status}", "created_at": created_at}]}

    def add_notification(self, email, message, issue_id):
        notification = {"id": str(uuid.uuid4()), "email": email, "message": message, "issue_id": issue_id, "created_at": now(), "read": False}
        self.notifications.insert(0, notification)
        if self.firestore:
            self.firestore.collection("notifications").document(notification["id"]).set({**notification, "created_at": firestore.SERVER_TIMESTAMP})

    def persist_issue(self, issue):
        if self.firestore:
            self.firestore.collection("issues").document(issue["id"]).set(issue)

    def persist_feedback(self, feedback):
        if self.firestore:
            self.firestore.collection("feedback").add(feedback)

    def next_id(self):
        numeric_ids = [int(re.sub(r"\D", "", issue_id)) for issue_id in self.issues]
        return f"CF-{max(numeric_ids or [1023]) + 1}"

    def notify_admins(self, message, issue_id):
        for user in self.users.values():
            if user["role"] == "Admin":
                self.add_notification(user["email"], message, issue_id)


store = Store()


def current_user():
    email = session.get("email")
    return store.users.get(email) if email else None


def require_login(role=None):
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or (role and user["role"] != role):
                return jsonify({"error": "Authentication required"}), 401
            return func(*args, **kwargs)
        return wrapped
    return decorator


def ai_analyze(title, description, location):
    text = f"{title} {description} {location}".lower()
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        prompt = "Return JSON only with keys category, priority, department, summary, reason, confidence. Categories: " + ", ".join(CATEGORIES) + ". Departments: " + ", ".join(DEPARTMENTS) + f". Issue title: {title}. Description: {description}. Location: {location}."
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}).encode()
        try:
            request = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=8) as response:
                candidate = json.loads(json.loads(response.read())["candidates"][0]["content"]["parts"][0]["text"])
                if candidate.get("category") in CATEGORIES and candidate.get("priority") in SLA_HOURS and candidate.get("department") in DEPARTMENTS:
                    return candidate
        except Exception:
            pass
    if any(word in text for word in ("wifi", "wi-fi", "network", "internet")):
        category, department = "Network", "IT Support"
    elif any(word in text for word in ("projector", "speaker", "display", "classroom")):
        category, department = "Classroom Equipment", "IT Support"
    elif any(word in text for word in ("clean", "washroom", "garbage", "hygiene")):
        category, department = "Cleanliness", "Housekeeping"
    elif any(word in text for word in ("leak", "door", "chair", "ceiling", "wall")):
        category, department = "Infrastructure", "Facilities"
    elif any(word in text for word in ("fan", "power", "light", "electric")):
        category, department = "Electrical", "Electrical Services"
    elif any(word in text for word in ("computer", "lab", "boot")):
        category, department = "Lab Equipment", "Lab Operations"
    else:
        category, department = "Other", "Facilities"
    priority = "Critical" if any(word in text for word in ("urgent", "30 minutes", "exam", "safety", "fire")) else ("High" if any(word in text for word in ("not working", "broken", "leak", "unable")) else "Medium")
    summary = title.strip() or description[:70].strip()
    reason = f"Detected {category.lower()} signals and routed to {department}. Priority reflects the reported impact and urgency."
    return {"category": category, "priority": priority, "department": department, "summary": summary, "reason": reason, "confidence": 91}


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/login")
def login():
    data = request.get_json() or {}
    identity = data.get("email", "").lower()
    user = store.users.get(identity) or next((item for item in store.users.values() if item.get("username", "").lower() == identity), None)
    if not user or user["password"] != data.get("password"):
        return jsonify({"error": "Invalid demo credentials"}), 401
    session["email"] = user["email"]
    return jsonify({"user": {k: user[k] for k in ("email", "name", "role")}})


@app.post("/api/register")
def register():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    identity = data.get("email", "").strip().lower()
    password = data.get("password", "")
    if not name or not identity or not password:
        return jsonify({"error": "Full name, email or username, and password are required"}), 400
    if len(password) < 6 or password != data.get("confirm_password"):
        return jsonify({"error": "Passwords must match and contain at least 6 characters"}), 400
    if "@" in identity and (" " in identity or "." not in identity.split("@", 1)[1]):
        return jsonify({"error": "Enter a valid email or username"}), 400
    if identity in store.users or any(item.get("username", "").lower() == identity for item in store.users.values()):
        return jsonify({"error": "An account with that email or username already exists"}), 409
    user = {"email": identity if "@" in identity else f"{identity}@campus.local", "username": identity, "name": name, "role": "Student", "password": password}
    store.users[user["email"].lower()] = user
    store.persist_user(user)
    return jsonify({"user": {k: user[k] for k in ("email", "name", "role")}}), 201


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
def me():
    user = current_user()
    return jsonify({"user": {k: user[k] for k in ("email", "name", "role")} if user else None})


@app.get("/api/meta")
def meta():
    return jsonify({"categories": CATEGORIES, "departments": DEPARTMENTS, "staff": STAFF, "sla": SLA_HOURS})


@app.post("/api/ai/analyze")
@require_login("Student")
def analyze():
    data = request.get_json() or {}
    return jsonify(ai_analyze(data.get("title", ""), data.get("description", ""), data.get("location", "")))


@app.get("/api/issues")
@require_login()
def list_issues():
    user = current_user()
    issues = list(store.issues.values())
    if user["role"] == "Student":
        issues = [item for item in issues if item["student_email"] == user["email"]]
    query = request.args.get("q", "").lower()
    filters = {key: request.args.get(key, "") for key in ("category", "priority", "status", "department")}
    if query:
        issues = [item for item in issues if query in " ".join(str(item.get(key, "")) for key in ("id", "title", "student_name", "location")).lower()]
    for key, value in filters.items():
        if value:
            field = "assigned_department" if key == "department" else key
            issues = [item for item in issues if item.get(field) == value]
    return jsonify({"issues": [issue_view(item) for item in sorted(issues, key=lambda x: x["created_at"], reverse=True)]})


@app.post("/api/issues")
@require_login("Student")
def create_issue():
    data = request.form.to_dict() if request.content_type and request.content_type.startswith("multipart/") else (request.get_json() or {})
    required = ["title", "description", "location"]
    if any(not data.get(key) for key in required):
        return jsonify({"error": "Title, description and location are required"}), 400
    user = current_user()
    ai = json.loads(data["ai"]) if data.get("ai") else {}
    if not all(ai.get(key) for key in ("category", "priority", "department", "summary", "reason", "confidence")):
        ai = ai_analyze(data["title"], data["description"], data["location"])
    category = data.get("category") or ai["category"]
    priority = data.get("priority") or ai["priority"]
    department = data.get("department") or ai["department"]
    duplicate = None
    words = set(re.findall(r"[a-z]{4,}", f"{data['title']} {data['description']}".lower()))
    for existing in store.issues.values():
        existing_words = set(re.findall(r"[a-z]{4,}", f"{existing['title']} {existing['description']}".lower()))
        overlap = len(words & existing_words) / max(len(words | existing_words), 1)
        if overlap >= 0.3 and existing["status"] != "Resolved":
            duplicate = {"id": existing["id"], "status": existing["status"], "reporters": 1, "title": existing["title"]}
            break
    created_at = now()
    issue_id = store.next_id()
    image_data = data.get("image", "")
    uploaded = request.files.get("image_file")
    if uploaded and uploaded.filename:
        if uploaded.mimetype not in ALLOWED_IMAGE_TYPES or not secure_filename(uploaded.filename).lower().endswith((".jpg", ".jpeg", ".png")):
            return jsonify({"error": "Unsupported file. Please upload a JPG, JPEG, or PNG image."}), 400
        raw_image = uploaded.read(MAX_IMAGE_BYTES + 1)
        if len(raw_image) > MAX_IMAGE_BYTES:
            return jsonify({"error": "Image is too large. Please choose a file smaller than 2 MB."}), 400
        image_data = f"data:{uploaded.mimetype};base64,{base64.b64encode(raw_image).decode('ascii')}"
    issue = {"id": issue_id, "student_email": user["email"], "student_name": user["name"], "title": data["title"], "description": data["description"], "location": data["location"], "room": data.get("room", data["location"]), "category": category, "priority": priority, "ai_category": ai["category"], "ai_priority": ai["priority"], "ai_department": ai["department"], "ai_summary": ai["summary"], "ai_reason": ai["reason"], "ai_confidence": ai["confidence"], "assigned_department": department, "assigned_staff": "", "status": "Pending", "created_at": created_at, "updated_at": created_at, "due_at": created_at + timedelta(hours=SLA_HOURS.get(priority, 8)), "resolved_at": None, "feedback_rating": None, "feedback_comment": "", "image": image_data, "image_name": uploaded.filename if uploaded else "", "update_history": []}
    activity(issue, "Issue Created", "Issue created with status Pending", user)
    store.issues[issue_id] = issue
    store.persist_issue(issue)
    store.add_notification(user["email"], f"Issue {issue_id} was submitted successfully", issue_id)
    store.notify_admins(f"New issue {issue_id} created by {user['name']}", issue_id)
    return jsonify({"issue": issue_view(issue), "duplicate": duplicate}), 201


@app.patch("/api/issues/<issue_id>")
@require_login("Admin")
def update_issue(issue_id):
    issue = store.issues.get(issue_id)
    if not issue:
        return jsonify({"error": "Issue not found"}), 404
    if issue["status"] == "Resolved":
        return jsonify({"error": "Resolved issues are locked and cannot be changed"}), 409
    data = request.get_json() or {}
    if data.get("assigned_staff") and data["assigned_staff"] not in STAFF_NAMES:
        return jsonify({"error": "Please select a valid staff member"}), 400
    old_status = issue["status"]
    old_priority = issue["priority"]
    admin = current_user()
    changes = []
    events = []
    if data.get("update_note"):
        message = f"Admin added an update: {data['update_note']}"
        activity(issue, "Admin Update", message, admin)
        events.append(message)
    for key in ("priority", "status", "assigned_department", "assigned_staff"):
        if key in data and data[key] is not None:
            if issue.get(key) != data[key]:
                old_value = issue.get(key) or "Unassigned"
                label = {"assigned_department": "Department", "assigned_staff": "Staff", "status": "Status", "priority": "Priority"}.get(key, key.title())
                if key == "status":
                    event = "Status Changed"
                    message = f"Status changed from {old_value} to {data[key]}"
                elif key == "priority":
                    event = "Priority Changed"
                    message = f"Priority changed from {old_value} to {data[key]}"
                elif key == "assigned_department":
                    event = "Department Changed"
                    message = f"Department changed to {data[key]}"
                else:
                    event = "Assigned"
                    message = f"{label} changed to {data[key]}"
                activity(issue, event, message, admin)
                changes.append(message)
                events.append(message)
            issue[key] = data[key]
    if issue["priority"] != old_priority:
        issue["due_at"] = issue["created_at"] + timedelta(hours=SLA_HOURS.get(issue["priority"], 8))
    if issue["status"] == "Resolved" and old_status != "Resolved":
        issue["resolved_at"] = now()
        activity(issue, "Resolved", "Issue marked as Resolved", admin)
        events.append("Issue marked as Resolved")
        store.add_notification(issue["student_email"], f"Your issue {issue_id} has been resolved", issue_id)
    for change in events:
        store.add_notification(issue["student_email"], f"Issue {issue_id} updated: {change}", issue_id)
    issue["updated_at"] = now()
    store.persist_issue(issue)
    return jsonify({"issue": issue_view(issue)})


@app.post("/api/issues/<issue_id>/reopen")
@require_login("Student")
def reopen_issue(issue_id):
    issue = store.issues.get(issue_id)
    user = current_user()
    if not issue or issue["student_email"] != user["email"]:
        return jsonify({"error": "Issue not found"}), 404
    if issue["status"] != "Resolved":
        return jsonify({"error": "Only resolved issues can be reopened"}), 409
    issue["status"] = "Reopened"
    issue["resolved_at"] = None
    issue["updated_at"] = now()
    activity(issue, "Reopened", "Student reopened the issue because the problem is not fixed", user)
    store.persist_issue(issue)
    store.notify_admins(f"Issue {issue_id} was reopened by {user['name']}", issue_id)
    return jsonify({"issue": issue_view(issue)})


@app.post("/api/issues/<issue_id>/feedback")
@require_login("Student")
def add_feedback(issue_id):
    issue = store.issues.get(issue_id)
    data = request.get_json() or {}
    if not issue or issue["student_email"] != current_user()["email"] or issue["status"] != "Resolved":
        return jsonify({"error": "Feedback is only available for your resolved issues"}), 400
    issue["feedback_rating"] = max(1, min(5, int(data.get("rating", 5))))
    issue["feedback_comment"] = data.get("comment", "")
    activity(issue, "Feedback Submitted", f"Student submitted a {issue['feedback_rating']}/5 rating", current_user())
    feedback = {"issue_id": issue_id, "student_email": current_user()["email"], "rating": issue["feedback_rating"], "comment": issue["feedback_comment"], "created_at": now()}
    store.feedback.append(feedback)
    store.persist_feedback(feedback)
    store.persist_issue(issue)
    return jsonify({"issue": issue_view(issue)})


@app.get("/api/notifications")
@require_login()
def notifications():
    return jsonify({"notifications": [{**item, "created_at": iso(item["created_at"])} for item in store.notifications if item["email"] == current_user()["email"]][:20]})


@app.get("/api/analytics")
@require_login("Admin")
def analytics():
    issues = list(store.issues.values())
    def counts(field):
        return {value: sum(1 for item in issues if item.get(field) == value) for value in sorted(set(item.get(field) for item in issues if item.get(field)))}
    resolved = [issue_view(item) for item in issues if item["status"] == "Resolved" and item.get("resolved_at")]
    ratings = [item["feedback_rating"] for item in issues if item.get("feedback_rating")]
    return jsonify({"by_category": counts("category"), "by_priority": counts("priority"), "by_status": counts("status"), "by_department": counts("assigned_department"), "overdue": sum(1 for item in issues if issue_view(item)["overdue"]), "average_resolution_hours": round(sum(item["resolution_hours"] for item in resolved) / len(resolved), 1) if resolved else 0, "satisfaction": round(sum(ratings) / len(ratings), 1) if ratings else 0, "rating_count": len(ratings)})


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", 5000)))