import os
import sqlite3
import secrets
from datetime import datetime

from flask import (Flask, jsonify, render_template, redirect, url_for,
                   request, flash, session, g, abort)
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

login_manager = LoginManager(app)
login_manager.login_view = "admin_login"
login_manager.login_message = "กรุณา login ก่อนเข้าใช้งาน"

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "accidents.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

THAI_MONTHS = {
    1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
    5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
    9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."
}

ACCIDENT_TYPES_INJURED = [
    "กระแทก",
    "มีด / กรรไกร",
    "เครื่องจักรหนีบ",
    "เครื่องจักรดึง",
    "ลื่น / ล้ม",
    "สารเคมี",
    "ตกจากที่สูง",
    "อื่น ๆ",
]

ACCIDENT_TYPES_NOT_INJURED = [
    "ยานพาหนะ",
    "เครื่องจักร",
    "ความร้อน",
    "ไฟฟ้า",
    "สิ่งมีพิษ สารเคมี",
    "วัตถุหรือสิ่งของกระแทก",
    "ยกของหนัก",
    "อื่น ๆ",
]

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(exc=None):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables and default admin user if not present."""
    # Ensure DB file is writable (guard against accidental read-only flag)
    if os.path.exists(DB_PATH):
        import stat
        os.chmod(DB_PATH, os.stat(DB_PATH).st_mode | stat.S_IWRITE)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            date             TEXT    NOT NULL,
            time             TEXT,
            department       TEXT    NOT NULL,
            division         TEXT,
            person_name      TEXT    NOT NULL,
            position         TEXT,
            has_injured      INTEGER NOT NULL DEFAULT 1,
            accident_type    TEXT    NOT NULL,
            location         TEXT,
            body_part        TEXT,
            description      TEXT    NOT NULL,
            corrective_action TEXT,
            score1           INTEGER NOT NULL DEFAULT 1,
            score2           INTEGER NOT NULL DEFAULT 1,
            score3           INTEGER NOT NULL DEFAULT 1,
            score4           INTEGER NOT NULL DEFAULT 1,
            score5           INTEGER NOT NULL DEFAULT 1,
            score_total      INTEGER NOT NULL DEFAULT 5,
            is_major         INTEGER NOT NULL DEFAULT 0,
            classification   TEXT    NOT NULL DEFAULT 'Non-accident',
            created_by       TEXT,
            created_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            role          TEXT    NOT NULL DEFAULT 'admin'
        );
    """)
    # Migrate: add location column if not present
    try:
        db.execute("ALTER TABLE incidents ADD COLUMN location TEXT")
        db.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    # Create default admin if not exists
    existing = db.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not existing:
        pw_hash = generate_password_hash("admin1234")
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", pw_hash, "admin")
        )
        db.commit()
    db.close()


def classify(score_total: int, is_major: bool) -> str:
    if is_major:
        return "Major"
    if score_total >= 18:
        return "Minor"
    return "Non-accident"


# ---------------------------------------------------------------------------
# Auth / User model
# ---------------------------------------------------------------------------

class User(UserMixin):
    def __init__(self, id_, username, role):
        self.id = id_
        self.username = username
        self.role = role


@login_manager.user_loader
def load_user(user_id):
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    db.close()
    if row:
        return User(row["id"], row["username"], row["role"])
    return None


# ---------------------------------------------------------------------------
# after_request: allow iframe embedding (Joomla)
# ---------------------------------------------------------------------------

@app.after_request
def allow_iframe(response):
    response.headers.pop("X-Frame-Options", None)
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    return response


# ===========================================================================
# PUBLIC ROUTES — Dashboard
# ===========================================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dashboard")
def api_dashboard():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM incidents ORDER BY date DESC, id DESC"
    ).fetchall()
    records = [dict(r) for r in rows]

    total = len(records)
    major_count   = sum(1 for r in records if r["classification"] == "Major")
    minor_count   = sum(1 for r in records if r["classification"] == "Minor")
    non_count     = sum(1 for r in records if r["classification"] == "Non-accident")

    # Monthly breakdown
    monthly_labels = list(THAI_MONTHS.values())
    monthly_major  = [0] * 12
    monthly_minor  = [0] * 12
    monthly_non    = [0] * 12
    for r in records:
        try:
            m = datetime.strptime(r["date"], "%Y-%m-%d").month - 1
        except Exception:
            continue
        if r["classification"] == "Major":
            monthly_major[m] += 1
        elif r["classification"] == "Minor":
            monthly_minor[m] += 1
        else:
            monthly_non[m] += 1

    # Department breakdown
    dept_map = {}
    for r in records:
        d = r["department"] or "-"
        dept_map[d] = dept_map.get(d, 0) + 1
    dept_labels = list(dept_map.keys())
    dept_values = list(dept_map.values())

    # Accident type breakdown — split by has_injured
    type_injured = {}
    type_not_injured = {}
    for r in records:
        t = r["accident_type"] or "-"
        if r["has_injured"]:
            type_injured[t] = type_injured.get(t, 0) + 1
        else:
            type_not_injured[t] = type_not_injured.get(t, 0) + 1

    injured_total     = sum(1 for r in records if r["has_injured"])
    not_injured_total = sum(1 for r in records if not r["has_injured"])

    return jsonify({
        "summary": {
            "total": total,
            "major": major_count,
            "minor": minor_count,
            "non_accident": non_count,
            "has_injured": injured_total,
            "not_injured": not_injured_total,
        },
        "monthly": {
            "labels": monthly_labels,
            "major": monthly_major,
            "minor": monthly_minor,
            "non_accident": monthly_non,
        },
        "by_dept": {"labels": dept_labels, "values": dept_values},
        "by_type_injured":     {"labels": list(type_injured.keys()),     "values": list(type_injured.values())},
        "by_type_not_injured": {"labels": list(type_not_injured.keys()), "values": list(type_not_injured.values())},
        "records": records,
    })


# ===========================================================================
# ADMIN AUTH
# ===========================================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        row = db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            user = User(row["id"], row["username"], row["role"])
            login_user(user)
            return redirect(url_for("admin_index"))
        flash("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", "danger")
    return render_template("admin/login.html")


@app.route("/admin/logout")
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for("admin_login"))


# ===========================================================================
# ADMIN CRUD
# ===========================================================================

@app.route("/admin")
@login_required
def admin_index():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM incidents ORDER BY date DESC, id DESC"
    ).fetchall()
    return render_template("admin/index.html", incidents=[dict(r) for r in rows])


@app.route("/admin/incident/new", methods=["GET", "POST"])
@login_required
def admin_new():
    if request.method == "POST":
        _save_incident(None)
        flash("บันทึกรายการใหม่เรียบร้อยแล้ว", "success")
        return redirect(url_for("admin_index"))
    return render_template("admin/form.html", incident=None)


@app.route("/admin/incident/<int:inc_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit(inc_id):
    db = get_db()
    row = db.execute("SELECT * FROM incidents WHERE id = ?", (inc_id,)).fetchone()
    if not row:
        abort(404)
    if request.method == "POST":
        _save_incident(inc_id)
        flash("แก้ไขรายการเรียบร้อยแล้ว", "success")
        return redirect(url_for("admin_index"))
    return render_template("admin/form.html", incident=dict(row))


@app.route("/admin/incident/<int:inc_id>/delete", methods=["POST"])
@login_required
def admin_delete(inc_id):
    db = get_db()
    db.execute("DELETE FROM incidents WHERE id = ?", (inc_id,))
    db.commit()
    flash("ลบรายการเรียบร้อยแล้ว", "success")
    return redirect(url_for("admin_index"))


# ---------------------------------------------------------------------------
# Helper: parse form and save incident
# ---------------------------------------------------------------------------

def _get_score(f, name):
    try:
        return max(1, min(9, int(f.get(name) or 1)))
    except (ValueError, TypeError):
        return 1


def _save_incident(inc_id):
    f = request.form
    has_injured = 1 if f.get("has_injured") == "1" else 0
    s1 = _get_score(f, "score1")
    s2 = _get_score(f, "score2")
    s3 = _get_score(f, "score3")
    s4 = _get_score(f, "score4")
    s5 = _get_score(f, "score5")
    total = s1 + s2 + s3 + s4 + s5
    is_major = 1 if f.get("is_major") else 0
    cls = classify(total, bool(is_major))

    db = get_db()
    if inc_id is None:
        db.execute(
            """INSERT INTO incidents
               (date, time, department, division, person_name, position,
                has_injured, accident_type, location, body_part, description, corrective_action,
                score1, score2, score3, score4, score5, score_total,
                is_major, classification, created_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f.get("date"), f.get("time"), f.get("department"),
                f.get("division"), f.get("person_name"), f.get("position"),
                has_injured, f.get("accident_type"), f.get("location"), f.get("body_part"),
                f.get("description"), f.get("corrective_action"),
                s1, s2, s3, s4, s5, total, is_major, cls,
                current_user.username,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
    else:
        db.execute(
            """UPDATE incidents SET
               date=?, time=?, department=?, division=?, person_name=?,
               position=?, has_injured=?, accident_type=?, location=?, body_part=?,
               description=?, corrective_action=?,
               score1=?, score2=?, score3=?, score4=?,
               score5=?, score_total=?, is_major=?, classification=?
               WHERE id=?""",
            (
                f.get("date"), f.get("time"), f.get("department"),
                f.get("division"), f.get("person_name"), f.get("position"),
                has_injured, f.get("accident_type"), f.get("location"), f.get("body_part"),
                f.get("description"), f.get("corrective_action"),
                s1, s2, s3, s4, s5, total, is_major, cls, inc_id,
            )
        )
    db.commit()


# ===========================================================================
# ADMIN — User Management
# ===========================================================================

@app.route("/admin/users")
@login_required
def admin_users():
    db = get_db()
    users = [dict(r) for r in db.execute("SELECT id, username, role FROM users ORDER BY id").fetchall()]
    return render_template("admin/users.html", users=users)


@app.route("/admin/users/new", methods=["POST"])
@login_required
def admin_user_new():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role     = request.form.get("role", "admin").strip()

    if not username or not password:
        flash("กรุณากรอกชื่อผู้ใช้และรหัสผ่าน", "danger")
        return redirect(url_for("admin_users"))

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        flash(f"ชื่อผู้ใช้ '{username}' มีอยู่แล้ว", "danger")
        return redirect(url_for("admin_users"))

    db.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, generate_password_hash(password), role)
    )
    db.commit()
    flash(f"เพิ่มผู้ใช้ '{username}' เรียบร้อยแล้ว", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/change-password", methods=["POST"])
@login_required
def admin_user_change_password(uid):
    new_pw = request.form.get("new_password", "")
    if not new_pw:
        flash("กรุณากรอกรหัสผ่านใหม่", "danger")
        return redirect(url_for("admin_users"))

    db = get_db()
    row = db.execute("SELECT id, username FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        abort(404)
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_pw), uid)
    )
    db.commit()
    flash(f"เปลี่ยนรหัสผ่านของ '{row['username']}' เรียบร้อยแล้ว", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:uid>/delete", methods=["POST"])
@login_required
def admin_user_delete(uid):
    if uid == current_user.id:
        flash("ไม่สามารถลบบัญชีของตัวเองได้", "danger")
        return redirect(url_for("admin_users"))

    db = get_db()
    row = db.execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        abort(404)
    db.execute("DELETE FROM users WHERE id = ?", (uid,))
    db.commit()
    flash(f"ลบผู้ใช้ '{row['username']}' เรียบร้อยแล้ว", "success")
    return redirect(url_for("admin_users"))


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000, host="0.0.0.0")
