"""
In a Tree - a free 18+ Texas dating web app.
No payments, no premium tiers, no paywalls. Ever.

Run:  pip install -r requirements.txt && python app.py
"""
import os
import re
import sqlite3
import uuid
from datetime import datetime
from functools import wraps

from flask import (
    Flask, g, request, jsonify, session,
    render_template, abort,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "dating.db"))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
DEMO_MODE = os.environ.get("DEMO_MODE", "false").strip().lower() == "true"
ALLOWED_PHOTO_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}

TEXAS_CITIES = [
    "Abilene", "Amarillo", "Arlington", "Austin", "Beaumont", "Brownsville",
    "College Station", "Corpus Christi", "Dallas", "Denton", "El Paso",
    "Fort Worth", "Frisco", "Garland", "Grand Prairie", "Houston",
    "Irving", "Laredo", "Lubbock", "McAllen", "McKinney", "Mesquite",
    "Midland", "Odessa", "Pasadena", "Plano", "San Angelo", "San Antonio",
    "Tyler", "Waco", "Wichita Falls",
]

GENDERS = ["Woman", "Man", "Nonbinary", "Other"]

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB photo uploads
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with open(os.path.join(BASE_DIR, "schema.sql")) as f:
        db.executescript(f.read())
    db.commit()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    user = query("SELECT * FROM users WHERE id = ?", (uid,), one=True)
    if user and user["is_banned"]:
        session.clear()
        return None
    return user


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return jsonify({"error": "Login required."}), 401
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user["is_admin"]:
            return jsonify({"error": "Admin only."}), 403
        return f(*args, **kwargs)
    return wrapper


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def public_profile_row(row):
    """Shape a profile row for the API. Never leaks email or password hash."""
    return {
        "user_id": row["user_id"],
        "display_name": row["display_name"],
        "age": row["age"],
        "gender": row["gender"],
        "city": row["city"],
        "bio": row["bio"],
        "interests": row["interests"],
        "looking_for": row["looking_for"],
        "photo_url": ("/static/uploads/" + row["photo_path"]) if row["photo_path"] else None,
        "is_demo": bool(row["is_demo"]),
    }


def blocked_pair(a, b):
    return query(
        "SELECT 1 FROM blocks WHERE (blocker_id = ? AND blocked_id = ?)"
        " OR (blocker_id = ? AND blocked_id = ?)",
        (a, b, b, a), one=True,
    ) is not None


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------
@app.post("/api/signup")
def api_signup():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip()
    age = data.get("age")
    gender = data.get("gender") or ""
    city = data.get("city") or ""

    if not EMAIL_RE.match(email):
        return jsonify({"error": "Enter a valid email address."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if not display_name or len(display_name) > 40:
        return jsonify({"error": "Display name is required (max 40 characters)."}), 400
    try:
        age = int(age)
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid age."}), 400
    if age < 18:
        return jsonify({"error": "You must be 18 or older to join."}), 400
    if gender not in GENDERS:
        return jsonify({"error": "Select a gender."}), 400
    if city not in TEXAS_CITIES:
        return jsonify({"error": "Select a Texas city."}), 400
    if query("SELECT id FROM users WHERE email = ?", (email,), one=True):
        return jsonify({"error": "That email is already registered. Try logging in."}), 400

    is_admin = 1 if (ADMIN_EMAIL and email == ADMIN_EMAIL) else 0
    user_id = execute(
        "INSERT INTO users (email, password_hash, is_admin) VALUES (?, ?, ?)",
        (email, generate_password_hash(password), is_admin),
    )
    execute(
        "INSERT INTO profiles (user_id, display_name, age, gender, city)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, display_name, age, gender, city),
    )
    session["user_id"] = user_id
    return jsonify({"ok": True, "user_id": user_id})


@app.post("/api/login")
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = query("SELECT * FROM users WHERE email = ?", (email,), one=True)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Wrong email or password."}), 401
    if user["is_banned"]:
        return jsonify({"error": "This account has been banned."}), 403
    session["user_id"] = user["id"]
    return jsonify({"ok": True})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/me")
def api_me():
    user = current_user()
    if not user:
        return jsonify({"user": None})
    profile = query("SELECT * FROM profiles WHERE user_id = ?", (user["id"],), one=True)
    return jsonify({
        "user": {
            "id": user["id"],
            "email": user["email"],
            "is_admin": bool(user["is_admin"]),
            "profile": public_profile_row(profile) if profile else None,
        }
    })


# ---------------------------------------------------------------------------
# Profiles API
# ---------------------------------------------------------------------------
@app.get("/api/profile")
@login_required
def api_get_profile():
    user = current_user()
    profile = query("SELECT * FROM profiles WHERE user_id = ?", (user["id"],), one=True)
    return jsonify({"profile": public_profile_row(profile)})


@app.put("/api/profile")
@login_required
def api_update_profile():
    user = current_user()
    data = request.get_json(force=True, silent=True) or {}
    display_name = (data.get("display_name") or "").strip()
    age = data.get("age")
    gender = data.get("gender") or ""
    city = data.get("city") or ""
    bio = (data.get("bio") or "").strip()[:500]
    interests = (data.get("interests") or "").strip()[:300]
    looking_for = (data.get("looking_for") or "").strip()[:300]

    if not display_name or len(display_name) > 40:
        return jsonify({"error": "Display name is required (max 40 characters)."}), 400
    try:
        age = int(age)
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid age."}), 400
    if age < 18:
        return jsonify({"error": "You must be 18 or older."}), 400
    if gender not in GENDERS:
        return jsonify({"error": "Select a gender."}), 400
    if city not in TEXAS_CITIES:
        return jsonify({"error": "Select a Texas city."}), 400

    execute(
        "UPDATE profiles SET display_name = ?, age = ?, gender = ?, city = ?,"
        " bio = ?, interests = ?, looking_for = ?,"
        " updated_at = datetime('now') WHERE user_id = ?",
        (display_name, age, gender, city, bio, interests, looking_for, user["id"]),
    )
    return jsonify({"ok": True})


@app.post("/api/profile/photo")
@login_required
def api_upload_photo():
    user = current_user()
    if "photo" not in request.files:
        return jsonify({"error": "No photo attached."}), 400
    file = request.files["photo"]
    if not file.filename:
        return jsonify({"error": "No photo selected."}), 400
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_PHOTO_EXTS:
        return jsonify({"error": "Photo must be PNG, JPG, GIF or WEBP."}), 400
    filename = f"{user['id']}_{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOAD_DIR, filename))
    # remove old photo file if any
    old = query("SELECT photo_path FROM profiles WHERE user_id = ?", (user["id"],), one=True)
    if old and old["photo_path"]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, os.path.basename(old["photo_path"])))
        except OSError:
            pass
    execute("UPDATE profiles SET photo_path = ? WHERE user_id = ?", (filename, user["id"]))
    return jsonify({"ok": True, "photo_url": "/static/uploads/" + filename})


# ---------------------------------------------------------------------------
# Browse / like / matches
# ---------------------------------------------------------------------------
@app.get("/api/browse")
@login_required
def api_browse():
    """Next batch of profiles the user hasn't liked/passed yet."""
    user = current_user()
    rows = query(
        """
        SELECT p.* FROM profiles p
        JOIN users u ON u.id = p.user_id
        WHERE p.user_id != ?
          AND u.is_banned = 0
          AND p.user_id NOT IN (SELECT liked_id FROM likes WHERE liker_id = ?)
          AND p.user_id NOT IN (SELECT blocked_id FROM blocks WHERE blocker_id = ?)
          AND p.user_id NOT IN (SELECT blocker_id FROM blocks WHERE blocked_id = ?)
        ORDER BY p.updated_at DESC
        LIMIT 20
        """,
        (user["id"], user["id"], user["id"], user["id"]),
    )
    return jsonify({"profiles": [public_profile_row(r) for r in rows]})


@app.post("/api/like")
@login_required
def api_like():
    user = current_user()
    data = request.get_json(force=True, silent=True) or {}
    try:
        target_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid profile."}), 400
    liked = bool(data.get("liked", True))
    if target_id == user["id"]:
        return jsonify({"error": "You can't like yourself."}), 400
    target = query(
        "SELECT u.is_banned FROM users u JOIN profiles p ON p.user_id = u.id"
        " WHERE u.id = ?",
        (target_id,), one=True,
    )
    if not target or target["is_banned"]:
        return jsonify({"error": "Profile not found."}), 404
    if blocked_pair(user["id"], target_id):
        return jsonify({"error": "Profile not found."}), 404

    execute(
        "INSERT INTO likes (liker_id, liked_id, liked) VALUES (?, ?, ?)"
        " ON CONFLICT(liker_id, liked_id) DO UPDATE SET liked = excluded.liked",
        (user["id"], target_id, 1 if liked else 0),
    )

    matched = False
    if liked:
        mutual = query(
            "SELECT 1 FROM likes WHERE liker_id = ? AND liked_id = ? AND liked = 1",
            (target_id, user["id"]), one=True,
        )
        if mutual:
            u1, u2 = sorted((user["id"], target_id))
            execute(
                "INSERT INTO matches (user1_id, user2_id) VALUES (?, ?)"
                " ON CONFLICT(user1_id, user2_id) DO NOTHING",
                (u1, u2),
            )
            matched = True
    return jsonify({"ok": True, "matched": matched})


def match_partner(match_row, me_id):
    partner_id = match_row["user2_id"] if match_row["user1_id"] == me_id else match_row["user1_id"]
    profile = query("SELECT * FROM profiles WHERE user_id = ?", (partner_id,), one=True)
    last_msg = query(
        "SELECT body, created_at FROM messages WHERE match_id = ?"
        " ORDER BY id DESC LIMIT 1",
        (match_row["id"],), one=True,
    )
    return {
        "match_id": match_row["id"],
        "created_at": match_row["created_at"],
        "partner": public_profile_row(profile) if profile else None,
        "last_message": dict(last_msg) if last_msg else None,
    }


@app.get("/api/matches")
@login_required
def api_matches():
    user = current_user()
    rows = query(
        "SELECT * FROM matches WHERE user1_id = ? OR user2_id = ?"
        " ORDER BY created_at DESC",
        (user["id"], user["id"]),
    )
    out = []
    for m in rows:
        partner_id = m["user2_id"] if m["user1_id"] == user["id"] else m["user1_id"]
        if blocked_pair(user["id"], partner_id):
            continue
        out.append(match_partner(m, user["id"]))
    return jsonify({"matches": out})


# ---------------------------------------------------------------------------
# Messaging (matched users only)
# ---------------------------------------------------------------------------
def get_match_or_404(match_id, me_id):
    m = query("SELECT * FROM matches WHERE id = ?", (match_id,), one=True)
    if not m or me_id not in (m["user1_id"], m["user2_id"]):
        abort(404)
    partner_id = m["user2_id"] if m["user1_id"] == me_id else m["user1_id"]
    if blocked_pair(me_id, partner_id):
        abort(404)
    return m, partner_id


@app.get("/api/matches/<int:match_id>")
@login_required
def api_match_detail(match_id):
    user = current_user()
    m, _ = get_match_or_404(match_id, user["id"])
    return jsonify({"match": match_partner(m, user["id"])})


@app.get("/api/matches/<int:match_id>/messages")
@login_required
def api_get_messages(match_id):
    user = current_user()
    m, _ = get_match_or_404(match_id, user["id"])
    after = request.args.get("after", "0")
    try:
        after_id = int(after)
    except ValueError:
        after_id = 0
    rows = query(
        "SELECT id, sender_id, body, created_at FROM messages"
        " WHERE match_id = ? AND id > ? ORDER BY id ASC LIMIT 100",
        (m["id"], after_id),
    )
    return jsonify({"messages": [dict(r) for r in rows]})


@app.post("/api/matches/<int:match_id>/messages")
@login_required
def api_send_message(match_id):
    user = current_user()
    m, _ = get_match_or_404(match_id, user["id"])
    data = request.get_json(force=True, silent=True) or {}
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "Message can't be empty."}), 400
    if len(body) > 2000:
        return jsonify({"error": "Message is too long (max 2000 characters)."}), 400
    msg_id = execute(
        "INSERT INTO messages (match_id, sender_id, body) VALUES (?, ?, ?)",
        (m["id"], user["id"], body),
    )
    return jsonify({"ok": True, "id": msg_id})


# ---------------------------------------------------------------------------
# Safety: report + block
# ---------------------------------------------------------------------------
@app.post("/api/report")
@login_required
def api_report():
    user = current_user()
    data = request.get_json(force=True, silent=True) or {}
    try:
        reported_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid profile."}), 400
    reason = (data.get("reason") or "").strip()[:1000]
    if reported_id == user["id"]:
        return jsonify({"error": "You can't report yourself."}), 400
    if not reason:
        return jsonify({"error": "Tell us what happened."}), 400
    if not query("SELECT id FROM users WHERE id = ?", (reported_id,), one=True):
        return jsonify({"error": "Profile not found."}), 404
    execute(
        "INSERT INTO reports (reporter_id, reported_id, reason) VALUES (?, ?, ?)",
        (user["id"], reported_id, reason),
    )
    return jsonify({"ok": True})


@app.post("/api/block")
@login_required
def api_block():
    user = current_user()
    data = request.get_json(force=True, silent=True) or {}
    try:
        blocked_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid profile."}), 400
    if blocked_id == user["id"]:
        return jsonify({"error": "You can't block yourself."}), 400
    if not query("SELECT id FROM users WHERE id = ?", (blocked_id,), one=True):
        return jsonify({"error": "Profile not found."}), 404
    execute(
        "INSERT INTO blocks (blocker_id, blocked_id) VALUES (?, ?)"
        " ON CONFLICT DO NOTHING",
        (user["id"], blocked_id),
    )
    return jsonify({"ok": True})


@app.get("/api/blocks")
@login_required
def api_blocks():
    user = current_user()
    rows = query(
        "SELECT p.* FROM blocks b JOIN profiles p ON p.user_id = b.blocked_id"
        " WHERE b.blocker_id = ?",
        (user["id"],),
    )
    return jsonify({"blocked": [public_profile_row(r) for r in rows]})


@app.delete("/api/block/<int:blocked_id>")
@login_required
def api_unblock(blocked_id):
    user = current_user()
    execute(
        "DELETE FROM blocks WHERE blocker_id = ? AND blocked_id = ?",
        (user["id"], blocked_id),
    )
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@app.get("/api/admin/reports")
@admin_required
def api_admin_reports():
    status = request.args.get("status", "open")
    rows = query(
        """
        SELECT r.*, rp.display_name AS reported_name, rr.display_name AS reporter_name
        FROM reports r
        JOIN profiles rp ON rp.user_id = r.reported_id
        JOIN profiles rr ON rr.user_id = r.reporter_id
        WHERE r.status = ?
        ORDER BY r.created_at DESC
        """,
        (status,),
    )
    return jsonify({"reports": [dict(r) for r in rows]})


@app.post("/api/admin/reports/<int:report_id>")
@admin_required
def api_admin_report_action(report_id):
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action")
    report = query("SELECT * FROM reports WHERE id = ?", (report_id,), one=True)
    if not report:
        return jsonify({"error": "Report not found."}), 404
    if action == "dismiss":
        execute("UPDATE reports SET status = 'dismissed' WHERE id = ?", (report_id,))
    elif action == "ban":
        execute("UPDATE users SET is_banned = 1 WHERE id = ?", (report["reported_id"],))
        execute("UPDATE reports SET status = 'actioned' WHERE id = ?", (report_id,))
    else:
        return jsonify({"error": "Unknown action."}), 400
    return jsonify({"ok": True})


@app.get("/api/admin/stats")
@admin_required
def api_admin_stats():
    return jsonify({
        "users": query("SELECT COUNT(*) c FROM users", one=True)["c"],
        "banned": query("SELECT COUNT(*) c FROM users WHERE is_banned = 1", one=True)["c"],
        "matches": query("SELECT COUNT(*) c FROM matches", one=True)["c"],
        "messages": query("SELECT COUNT(*) c FROM messages", one=True)["c"],
        "open_reports": query(
            "SELECT COUNT(*) c FROM reports WHERE status = 'open'", one=True)["c"],
    })


# ---------------------------------------------------------------------------
# Demo mode (OFF by default; clearly-labeled fake data for testing only)
# ---------------------------------------------------------------------------
DEMO_PROFILES = [
    ("DEMO - Jessie", 29, "Woman", "Austin",
     "Demo profile for testing. Not a real person.",
     "Live music, tacos, two-stepping", "Something casual and fun"),
    ("DEMO - Colt", 34, "Man", "Dallas",
     "Demo profile for testing. Not a real person.",
     "BBQ, football, road trips", "No-strings fun"),
    ("DEMO - Marisol", 27, "Woman", "Houston",
     "Demo profile for testing. Not a real person.",
     "Dancing, late nights, good conversation", "Casual dating"),
]


def seed_demo():
    if query("SELECT COUNT(*) c FROM profiles WHERE is_demo = 1", one=True)["c"]:
        return
    for i, (name, age, gender, city, bio, interests, looking_for) in enumerate(DEMO_PROFILES):
        email = f"demo{i}@example.local"
        uid = execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, generate_password_hash("demo-password-" + str(i))),
        )
        execute(
            "INSERT INTO profiles (user_id, display_name, age, gender, city, bio,"
            " interests, looking_for, is_demo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (uid, name, age, gender, city, bio, interests, looking_for),
        )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/")
def page_index():
    return render_template("index.html", demo_mode=DEMO_MODE)


@app.get("/signup")
def page_signup():
    return render_template("signup.html", cities=TEXAS_CITIES, genders=GENDERS)


@app.get("/login")
def page_login():
    return render_template("login.html")


@app.get("/browse")
def page_browse():
    return render_template("browse.html")


@app.get("/profile")
def page_profile():
    return render_template("profile.html", cities=TEXAS_CITIES, genders=GENDERS)


@app.get("/matches")
def page_matches():
    return render_template("matches.html")


@app.get("/chat/<int:match_id>")
def page_chat(match_id):
    return render_template("chat.html", match_id=match_id)


@app.get("/safety")
def page_safety():
    return render_template("safety.html")


@app.get("/admin")
def page_admin():
    return render_template("admin.html")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
with app.app_context():
    init_db()
    if DEMO_MODE:
        seed_demo()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
