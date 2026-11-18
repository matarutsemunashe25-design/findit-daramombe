"""Daramombe FindIt - smart lost-and-found for school.

Run:  pip install -r requirements.txt && python app.py
Staff password (change before Open Day!):  set STAFF_PASSWORD env var.
"""
import os
import secrets
import sqlite3
from datetime import date
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("FINDIT_DB", os.path.join(BASE, "findit.db"))
STAFF_PASSWORD = os.environ.get("STAFF_PASSWORD", "daramombe2026")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

CATEGORIES = ["Calculator", "Water bottle", "Stationery", "Book / Notebook",
              "Bag", "Clothing", "Lunch box", "Electronics", "Keys / ID card",
              "Sports gear", "Other"]
COLOURS = ["Black", "Blue", "Red", "Green", "Yellow", "White", "Grey",
           "Pink", "Purple", "Orange", "Brown", "Multicolour"]
LOCATIONS = ["Classroom block A", "Classroom block B", "Computer lab",
             "Library", "Dining hall", "Tuckshop", "Sports field",
             "Chapel / Hall", "Dormitory", "Corridor / Other"]

MATCH_THRESHOLD = 50


# ---------------------------------------------------------------- database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK (kind IN ('lost', 'found')),
            code TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            colour TEXT NOT NULL,
            location TEXT NOT NULL,
            event_date TEXT NOT NULL,
            description TEXT,
            contact TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.commit()
    db.close()


init_db()


# ---------------------------------------------------------------- matching
def score(lost, found):
    """0-100 similarity. Category must match, otherwise 0."""
    if lost["category"] != found["category"]:
        return 0
    s = 40
    if lost["colour"] == found["colour"]:
        s += 25
    elif "Multicolour" in (lost["colour"], found["colour"]):
        s += 8
    if lost["location"] == found["location"]:
        s += 20
    days = abs((date.fromisoformat(found["event_date"]) -
                date.fromisoformat(lost["event_date"])).days)
    s += max(0, 15 - 5 * days)  # same day 15, 1 day 10, 2 days 5
    return s


def label(s):
    if s >= 80:
        return "Strong match"
    if s >= 65:
        return "Likely match"
    return "Possible match"


def find_matches(item):
    other = "found" if item["kind"] == "lost" else "lost"
    rows = get_db().execute(
        "SELECT * FROM items WHERE kind = ? AND status = 'open'",
        (other,)).fetchall()
    out = []
    for r in rows:
        s = score(item, r) if item["kind"] == "lost" else score(r, item)
        if s >= MATCH_THRESHOLD:
            out.append({"item": r, "score": s, "label": label(s)})
    return sorted(out, key=lambda m: m["score"], reverse=True)


# ---------------------------------------------------------------- helpers
def staff_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not session.get("staff"):
            flash("Staff login required.", "error")
            return redirect(url_for("staff_login"))
        return view(*a, **kw)
    return wrapped


def new_code(prefix):
    return f"{prefix}-{secrets.token_hex(3).upper()}"


def read_form():
    f = request.form
    data = {k: f.get(k, "").strip() for k in
            ("category", "colour", "location", "event_date",
             "description", "contact")}
    errors = []
    if data["category"] not in CATEGORIES:
        errors.append("Choose a category.")
    if data["colour"] not in COLOURS:
        errors.append("Choose a colour.")
    if data["location"] not in LOCATIONS:
        errors.append("Choose a location.")
    try:
        if date.fromisoformat(data["event_date"]) > date.today():
            errors.append("The date cannot be in the future.")
    except ValueError:
        errors.append("Enter a valid date.")
    return data, errors


def form_context(**extra):
    return dict(categories=CATEGORIES, colours=COLOURS, locations=LOCATIONS,
                today=date.today().isoformat(), **extra)


def insert_item(kind, data):
    code = new_code("L" if kind == "lost" else "F")
    db = get_db()
    db.execute(
        "INSERT INTO items (kind, code, category, colour, location, "
        "event_date, description, contact) VALUES (?,?,?,?,?,?,?,?)",
        (kind, code, data["category"], data["colour"], data["location"],
         data["event_date"], data["description"], data["contact"]))
    db.commit()
    return db.execute("SELECT * FROM items WHERE code = ?", (code,)).fetchone()


# ---------------------------------------------------------------- student side
@app.route("/")
def index():
    db = get_db()
    stats = {
        "lost": db.execute("SELECT COUNT(*) FROM items WHERE kind='lost' "
                           "AND status='open'").fetchone()[0],
        "found": db.execute("SELECT COUNT(*) FROM items WHERE kind='found' "
                            "AND status='open'").fetchone()[0],
        "returned": db.execute("SELECT COUNT(*) FROM items "
                               "WHERE kind='lost' AND status='returned'"
                               ).fetchone()[0],
    }
    return render_template("index.html", stats=stats)


@app.route("/lost", methods=["GET", "POST"])
def report_lost():
    if request.method == "POST":
        data, errors = read_form()
        if not data["contact"]:
            errors.append("Enter your name and class so staff can contact you.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("lost.html", **form_context(form=data))
        item = insert_item("lost", data)
        flash("Report saved. Keep your reference code!", "ok")
        return redirect(url_for("track", code=item["code"]))
    return render_template("lost.html", **form_context(form={}))


@app.route("/track", methods=["GET", "POST"])
def track_lookup():
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        return redirect(url_for("track", code=code))
    return render_template("track_lookup.html")


@app.route("/track/<code>")
def track(code):
    item = get_db().execute(
        "SELECT * FROM items WHERE code = ? AND kind = 'lost'",
        (code.upper(),)).fetchone()
    if item is None:
        flash("No lost report with that code.", "error")
        return redirect(url_for("track_lookup"))
    matches = find_matches(item) if item["status"] == "open" else []
    return render_template("track.html", item=item, matches=matches)


# ---------------------------------------------------------------- staff side
@app.route("/staff/login", methods=["GET", "POST"])
def staff_login():
    if request.method == "POST":
        if secrets.compare_digest(request.form.get("password", ""),
                                  STAFF_PASSWORD):
            session["staff"] = True
            return redirect(url_for("dashboard"))
        flash("Wrong password.", "error")
    return render_template("staff_login.html")


@app.route("/staff/logout")
def staff_logout():
    session.pop("staff", None)
    return redirect(url_for("index"))


@app.route("/staff")
@staff_required
def dashboard():
    db = get_db()
    lost = db.execute("SELECT * FROM items WHERE kind='lost' AND "
                      "status='open' ORDER BY created DESC").fetchall()
    found = db.execute("SELECT * FROM items WHERE kind='found' AND "
                       "status='open' ORDER BY created DESC").fetchall()
    lost_m = [(i, find_matches(i)) for i in lost]
    found_m = [(i, find_matches(i)) for i in found]
    return render_template("dashboard.html", lost_m=lost_m, found_m=found_m)


@app.route("/staff/found", methods=["GET", "POST"])
@staff_required
def register_found():
    if request.method == "POST":
        data, errors = read_form()
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("found.html", **form_context(form=data))
        item = insert_item("found", data)
        n = len(find_matches(item))
        flash(f"Found item {item['code']} registered. "
              f"{n} possible matching lost report(s).", "ok")
        return redirect(url_for("dashboard"))
    return render_template("found.html", **form_context(form={}))


@app.route("/staff/resolve", methods=["POST"])
@staff_required
def resolve():
    ids = [request.form.get("lost_id"), request.form.get("found_id")]
    db = get_db()
    for i in ids:
        if i and i.isdigit():
            db.execute("UPDATE items SET status='returned' WHERE id = ?", (i,))
    db.commit()
    flash("Marked as returned. 🎉", "ok")
    return redirect(url_for("dashboard"))


@app.route("/staff/reset", methods=["POST"])
@staff_required
def reset_demo():
    """Wipe everything and add a few background items for a clean demo."""
    db = get_db()
    db.execute("DELETE FROM items")
    seed = [
        ("lost", "Water bottle", "Blue", "Sports field", "Aisha, S3B"),
        ("found", "Water bottle", "Red", "Dining hall", None),
        ("found", "Stationery", "Black", "Library", None),
        ("lost", "Book / Notebook", "Green", "Classroom block A", "Eric, S2A"),
    ]
    today = date.today().isoformat()
    for kind, cat, col, loc, contact in seed:
        db.execute(
            "INSERT INTO items (kind, code, category, colour, location, "
            "event_date, description, contact) VALUES (?,?,?,?,?,?,?,?)",
            (kind, new_code("L" if kind == "lost" else "F"), cat, col, loc,
             today, "Demo item", contact))
    db.commit()
    flash("Demo data reset. Now report a lost calculator live!", "ok")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
