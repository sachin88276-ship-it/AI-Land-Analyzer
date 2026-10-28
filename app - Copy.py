
import os
import sqlite3
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "dev-only-change-this-secret-before-deployment"
)


def get_db():
    conn = sqlite3.connect("land_records.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS land_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT,
            area REAL,
            unit TEXT,
            land_type TEXT,
            budget REAL,
            purpose TEXT,
            details TEXT,
            price_per_sqft REAL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS saved_properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            location TEXT,
            area REAL,
            unit TEXT,
            land_type TEXT,
            budget REAL,
            purpose TEXT,
            details TEXT,
            price_per_sqft REAL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)

    return wrapped_view


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if len(username) < 3:
            return render_template(
                "register.html",
                error="Username must contain at least 3 characters."
            )

        if len(password) < 8:
            return render_template(
                "register.html",
                error="Password must contain at least 8 characters."
            )

        password_hash = generate_password_hash(password)
        conn = get_db()

        try:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, password_hash)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template(
                "register.html",
                error="Username already exists. Please choose another."
            )

        conn.close()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid username or password."
        )

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    records = conn.execute(
        "SELECT * FROM land_records ORDER BY id DESC"
    ).fetchall()
    conn.close()

    return render_template("dashboard.html", records=records)


@app.route("/analyzer")
@login_required
def analyzer():
    return render_template("analyzer.html")


@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    land = {
        "location": request.form.get("location", "").strip(),
        "area": request.form.get("area", ""),
        "unit": request.form.get("unit", ""),
        "land_type": request.form.get("land_type", ""),
        "budget": request.form.get("budget", ""),
        "purpose": request.form.get("purpose", ""),
        "details": request.form.get("details", "")
    }

    try:
        area = float(land["area"] or 0)
        budget = float(land["budget"] or 0)

        if area <= 0 or budget < 0:
            raise ValueError

    except (ValueError, TypeError):
        return "Please enter a valid area and a non-negative budget.", 400

    if land["unit"] == "sqft":
        area_sqft = area
    elif land["unit"] == "sqm":
        area_sqft = area * 10.7639
    elif land["unit"] == "acre":
        area_sqft = area * 43560
    elif land["unit"] == "guntha":
        area_sqft = area * 1089
    else:
        area_sqft = 0

    land["area_sqft"] = round(area_sqft, 2)
    land["price_per_sqft"] = (
        round(budget / area_sqft, 2)
        if area_sqft > 0 and budget > 0 else None
    )

    conn = get_db()
    conn.execute(
        """INSERT INTO land_records
        (location, area, unit, land_type, budget, purpose, details, price_per_sqft)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            land["location"],
            area,
            land["unit"],
            land["land_type"],
            budget,
            land["purpose"],
            land["details"],
            land["price_per_sqft"]
        )
    )
    conn.commit()
    conn.close()

    return render_template("result.html", land=land)


@app.route("/report")
@login_required
def report():
    land = {
        "location": request.args.get("location", "Not provided"),
        "area": request.args.get("area", "Not provided"),
        "unit": request.args.get("unit", "sqft"),
        "land_type": request.args.get("land_type", "Not provided"),
        "budget": request.args.get("budget", ""),
        "purpose": request.args.get("purpose", "Not provided"),
        "details": request.args.get("details", "")
    }

    try:
        area = float(land["area"] or 0)
        budget = float(land["budget"] or 0)
        unit = land["unit"].lower()

        if unit in ["sqft", "sq ft", "square feet"]:
            area_sqft = area
        elif unit in ["sqm", "sq m", "square meter", "square meters"]:
            area_sqft = area * 10.7639
        elif unit == "acre":
            area_sqft = area * 43560
        elif unit == "guntha":
            area_sqft = area * 1089
        else:
            area_sqft = 0

        land["price_per_sqft"] = (
            round(budget / area_sqft, 2)
            if area_sqft > 0 and budget > 0 else None
        )
    except (ValueError, TypeError):
        land["price_per_sqft"] = None

    return render_template("report.html", land=land)


@app.route("/compare", methods=["GET", "POST"])
@login_required
def compare():
    result = None

    if request.method == "POST":
        try:
            location_a = request.form.get("location_a", "").strip()
            location_b = request.form.get("location_b", "").strip()
            area_a = float(request.form.get("area_a", 0))
            area_b = float(request.form.get("area_b", 0))
            price_a = float(request.form.get("price_a", 0))
            price_b = float(request.form.get("price_b", 0))

            if (
                not location_a or not location_b
                or area_a <= 0 or area_b <= 0
                or price_a < 0 or price_b < 0
            ):
                raise ValueError

            rate_a = price_a / area_a
            rate_b = price_b / area_b

            if rate_a < rate_b:
                message = f"{location_a} has the lower price per sq ft."
            elif rate_b < rate_a:
                message = f"{location_b} has the lower price per sq ft."
            else:
                message = "Both properties have the same price per sq ft."

            result = {
                "location_a": location_a,
                "location_b": location_b,
                "area_a": area_a,
                "area_b": area_b,
                "price_a": price_a,
                "price_b": price_b,
                "rate_a": rate_a,
                "rate_b": rate_b,
                "message": message
            }

        except (ValueError, TypeError):
            return (
                "Please enter valid locations, positive areas "
                "and non-negative prices.",
                400
            )

    return render_template("compare.html", result=result)


@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    result = None

    if request.method == "POST":
        try:
            budget_amount = float(request.form.get("budget_amount", 0))
            land_price = float(request.form.get("land_price", 0))
            extra_cost = float(request.form.get("extra_cost", 0))

            if min(budget_amount, land_price, extra_cost) < 0:
                raise ValueError

            total_cost = land_price + extra_cost
            difference = budget_amount - total_cost

            result = {
                "budget": budget_amount,
                "total_cost": total_cost,
                "difference": difference
            }
        except (ValueError, TypeError):
            result = {"error": "Please enter valid non-negative amounts."}

    return render_template("budget.html", result=result)


@app.route("/documents")
@login_required
def documents():
    checklist = [
        "Sale deed / title deed",
        "Previous ownership records",
        "Property card or 7/12 extract, where applicable",
        "Encumbrance certificate, where applicable",
        "Approved land-use and zoning documents",
        "Property tax receipts",
        "Survey map and boundary details",
        "Identity documents of the seller",
        "Required permissions and NOCs, where applicable"
    ]
    return render_template("documents.html", checklist=checklist)


@app.route("/price-charts")
@login_required
def price_charts():
    return render_template("price_charts.html")


@app.route("/save-property", methods=["POST"])
@login_required
def save_property():
    try:
        location = request.form.get("location", "").strip()
        area = float(request.form.get("area", 0))
        unit = request.form.get("unit", "sqft")
        land_type = request.form.get("land_type", "")
        budget = float(request.form.get("budget", 0))
        purpose = request.form.get("purpose", "")
        details = request.form.get("details", "")
        raw_rate = request.form.get("price_per_sqft", "")
        price_per_sqft = float(raw_rate) if raw_rate else None

        if not location or area <= 0 or budget < 0:
            raise ValueError

        conn = get_db()
        conn.execute(
            """INSERT INTO saved_properties
            (user_id, location, area, unit, land_type, budget,
             purpose, details, price_per_sqft)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session["user_id"], location, area, unit, land_type,
                budget, purpose, details, price_per_sqft
            )
        )
        conn.commit()
        conn.close()

    except (ValueError, TypeError):
        return "Invalid property details. Please check the values.", 400

    flash("Property saved successfully.", "success")
    return redirect(url_for("saved_properties"))


@app.route("/saved-properties")
@login_required
def saved_properties():
    conn = get_db()
    properties = conn.execute(
        """SELECT * FROM saved_properties
        WHERE user_id = ?
        ORDER BY id DESC""",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    return render_template(
        "saved_properties.html",
        properties=properties
    )


@app.route("/delete-saved-property/<int:property_id>", methods=["POST"])
@login_required
def delete_saved_property(property_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM saved_properties WHERE id = ? AND user_id = ?",
        (property_id, session["user_id"])
    )
    conn.commit()
    conn.close()

    flash("Property deleted if it belonged to your account.", "success")
    return redirect(url_for("saved_properties"))


if __name__ == "__main__":
    app.run(debug=True)
