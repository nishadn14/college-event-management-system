import csv
import io
import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (Flask, Response, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "events.db")

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

CATEGORIES = ["Technical", "Cultural", "Sports", "Workshop", "Seminar", "Other"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    usn TEXT UNIQUE NOT NULL,
    email TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student'
);
CREATE TABLE IF NOT EXISTS events(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    venue TEXT NOT NULL,
    event_date TEXT NOT NULL,
    event_time TEXT NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS registrations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    registered_at TEXT NOT NULL,
    UNIQUE(user_id, event_id)
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(SCHEMA)
    if not db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        db.execute("INSERT INTO users(name,usn,email,password_hash,role) VALUES(?,?,?,?,?)",
                   ("Administrator", "admin", "admin@college.edu", generate_password_hash("admin123"), "admin"))
    if not db.execute("SELECT 1 FROM events").fetchone():
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        db.executemany(
            "INSERT INTO events(title,description,category,venue,event_date,event_time,capacity,created_at) VALUES(?,?,?,?,?,?,?,?)",
            [("Hackathon 2027", "24-hour coding hackathon open to all departments.", "Technical",
              "Main Auditorium", "2027-02-10", "09:00", 100, now),
             ("Cultural Fest", "Dance, music and drama competitions.", "Cultural",
              "Open Air Theatre", "2027-03-05", "10:00", 300, now),
             ("ML Workshop", "Hands-on workshop on machine learning with Python.", "Workshop",
              "Seminar Hall", "2027-01-20", "14:00", 60, now)])
    db.commit()
    db.close()


def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if "user_id" not in session:
                flash("Please log in first.", "error")
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                flash("Access denied.", "error")
                return redirect(url_for("index"))
            return f(*a, **kw)
        return wrapper
    return deco


def today():
    return datetime.now().strftime("%Y-%m-%d")


@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("admin_dashboard" if session["role"] == "admin" else "events"))


# ---------- Auth ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        usn = request.form["usn"].strip().upper()
        email = request.form.get("email", "").strip()
        pw = request.form["password"]
        if not name or not usn or len(pw) < 4:
            flash("Fill all fields (password min 4 characters).", "error")
            return render_template("register.html")
        try:
            get_db().execute("INSERT INTO users(name,usn,email,password_hash) VALUES(?,?,?,?)",
                             (name, usn, email, generate_password_hash(pw)))
            get_db().commit()
        except sqlite3.IntegrityError:
            flash("That USN is already registered.", "error")
            return render_template("register.html")
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_db().execute("SELECT * FROM users WHERE UPPER(usn)=UPPER(?)",
                                (request.form["usn"].strip(),)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session.update(user_id=user["id"], name=user["name"], role=user["role"])
            return redirect(url_for("index"))
        flash("Invalid USN or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- Student ----------
@app.route("/events")
@login_required("student")
def events():
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "")
    sql = """SELECT e.*,
             (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS taken,
             (SELECT 1 FROM registrations r WHERE r.event_id=e.id AND r.user_id=?) AS joined
             FROM events e WHERE 1=1"""
    args = [session["user_id"]]
    if q:
        sql += " AND (e.title LIKE ? OR e.venue LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    if cat:
        sql += " AND e.category=?"
        args.append(cat)
    rows = get_db().execute(sql + " ORDER BY e.event_date, e.event_time", args).fetchall()
    return render_template("events.html", events=rows, categories=CATEGORIES, q=q, cat=cat, today=today())


@app.route("/events/<int:event_id>/register", methods=["POST"])
@login_required("student")
def register_event(event_id):
    db = get_db()
    ev = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        flash("Event not found.", "error")
    elif ev["event_date"] < today():
        flash("This event has already taken place.", "error")
    else:
        taken = db.execute("SELECT COUNT(*) FROM registrations WHERE event_id=?", (event_id,)).fetchone()[0]
        if taken >= ev["capacity"]:
            flash("Sorry, this event is full.", "error")
        else:
            try:
                db.execute("INSERT INTO registrations(user_id,event_id,registered_at) VALUES(?,?,?)",
                           (session["user_id"], event_id, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                flash(f"Registered for {ev['title']}.", "success")
            except sqlite3.IntegrityError:
                flash("You are already registered for this event.", "error")
    return redirect(request.referrer or url_for("events"))


@app.route("/events/<int:event_id>/cancel", methods=["POST"])
@login_required("student")
def cancel_registration(event_id):
    db = get_db()
    db.execute("DELETE FROM registrations WHERE user_id=? AND event_id=?", (session["user_id"], event_id))
    db.commit()
    flash("Registration cancelled.", "success")
    return redirect(request.referrer or url_for("my_events"))


@app.route("/my-events")
@login_required("student")
def my_events():
    rows = get_db().execute("""SELECT e.*, r.registered_at FROM registrations r
                               JOIN events e ON e.id=r.event_id WHERE r.user_id=?
                               ORDER BY e.event_date""", (session["user_id"],)).fetchall()
    return render_template("my_events.html", events=rows, today=today())


# ---------- Admin ----------
@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    db = get_db()
    stats = {
        "events": db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "upcoming": db.execute("SELECT COUNT(*) FROM events WHERE event_date>=?", (today(),)).fetchone()[0],
        "students": db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        "registrations": db.execute("SELECT COUNT(*) FROM registrations").fetchone()[0],
    }
    rows = db.execute("""SELECT e.*, (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS taken
                         FROM events e ORDER BY e.event_date DESC""").fetchall()
    return render_template("admin_dashboard.html", stats=stats, events=rows, today=today())


def _read_event_form():
    f = request.form
    title, venue = f["title"].strip(), f["venue"].strip()
    if not title or not venue or not f["event_date"] or not f["event_time"]:
        raise ValueError("Title, venue, date and time are required.")
    cap = int(f["capacity"])
    if cap < 1:
        raise ValueError("Capacity must be at least 1.")
    return (title, f.get("description", "").strip(), f["category"], venue,
            f["event_date"], f["event_time"], cap)


@app.route("/admin/event/new", methods=["GET", "POST"])
@login_required("admin")
def event_new():
    if request.method == "POST":
        try:
            data = _read_event_form()
        except (ValueError, KeyError) as e:
            flash(str(e) if isinstance(e, ValueError) and "required" in str(e) or "Capacity" in str(e)
                  else "Invalid input.", "error")
            return render_template("event_form.html", event=request.form, categories=CATEGORIES, mode="Add")
        get_db().execute("""INSERT INTO events(title,description,category,venue,event_date,event_time,capacity,created_at)
                            VALUES(?,?,?,?,?,?,?,?)""", (*data, datetime.now().strftime("%Y-%m-%d %H:%M")))
        get_db().commit()
        flash("Event created.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("event_form.html", event={}, categories=CATEGORIES, mode="Add")


@app.route("/admin/event/<int:event_id>/edit", methods=["GET", "POST"])
@login_required("admin")
def event_edit(event_id):
    db = get_db()
    ev = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        flash("Event not found.", "error")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        try:
            data = _read_event_form()
        except (ValueError, KeyError):
            flash("Invalid input. Check all fields.", "error")
            return render_template("event_form.html", event=request.form, categories=CATEGORIES, mode="Edit")
        db.execute("""UPDATE events SET title=?,description=?,category=?,venue=?,event_date=?,event_time=?,capacity=?
                      WHERE id=?""", (*data, event_id))
        db.commit()
        flash("Event updated.", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("event_form.html", event=ev, categories=CATEGORIES, mode="Edit")


@app.route("/admin/event/<int:event_id>/delete", methods=["POST"])
@login_required("admin")
def event_delete(event_id):
    get_db().execute("DELETE FROM events WHERE id=?", (event_id,))
    get_db().commit()
    flash("Event deleted.", "success")
    return redirect(url_for("admin_dashboard"))


def _participants(event_id):
    return get_db().execute("""SELECT u.name, u.usn, u.email, r.registered_at FROM registrations r
                               JOIN users u ON u.id=r.user_id WHERE r.event_id=?
                               ORDER BY r.registered_at""", (event_id,)).fetchall()


@app.route("/admin/event/<int:event_id>/participants")
@login_required("admin")
def participants(event_id):
    ev = get_db().execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        flash("Event not found.", "error")
        return redirect(url_for("admin_dashboard"))
    return render_template("participants.html", event=ev, rows=_participants(event_id))


@app.route("/admin/event/<int:event_id>/export")
@login_required("admin")
def export_participants(event_id):
    ev = get_db().execute("SELECT title FROM events WHERE id=?", (event_id,)).fetchone()
    if not ev:
        return redirect(url_for("admin_dashboard"))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Name", "USN", "Email", "Registered At"])
    for r in _participants(event_id):
        w.writerow([r["name"], r["usn"], r["email"], r["registered_at"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=participants_{event_id}.csv"})


init_db()

if __name__ == "__main__":
    app.run(debug=True)
