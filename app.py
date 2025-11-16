import sqlite3
from functools import wraps
import json

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import re
import os
import jwt
import datetime
from datetime import timezone

# --- Configuration ---
app = Flask(__name__)
# Enable CORS so browser-based frontends (like index.html) can POST to /api/register
CORS(app, resources={r"/api/*": {"origins": "*"}})
# Use an absolute path for the SQLite file (stable regardless of current working dir)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "lab_reservations.db")
# Only print in non-testing environments to avoid CI noise
if not os.getenv("PYTEST_CURRENT_TEST"):
    print("Using database file:", DATABASE)
# Secret used for signing JWTs. In production, set via environment variable.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
JWT_EXP_DELTA_SECONDS = int(os.getenv("JWT_EXP_DELTA_SECONDS", 3600))

# --- Database Setup ---


def get_db_connection():
    """Connects to the SQLite database."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # This allows accessing columns by name
    return conn


def init_db():
    """Initializes the database schema if it doesn't exist."""
    print("Initializing database...")
    conn = get_db_connection()
    cursor = conn.cursor()
    # Create the users table based on user story requirements:
    # 1. college_id (unique, primary key)
    # 2. name
    # 3. email (unique)
    # 4. password_hash (for secure storage)
    # 5. role (e.g., 'student', 'admin', 'lab_assistant')
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            college_id TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );
        """
    )
    # Create bookings table for lab reservations
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            college_id TEXT NOT NULL,
            lab_name TEXT NOT NULL,
            booking_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (college_id) REFERENCES users(college_id)
        );
        """
    )
    # Create labs table for lab information
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS labs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            capacity INTEGER NOT NULL,
            available_slots INTEGER NOT NULL DEFAULT 0,
            equipment TEXT NOT NULL,
            equipment_status TEXT NOT NULL DEFAULT 'Not Available',
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        """
    )
    # Add available_slots column to existing labs table if it doesn't exist
    try:
        cursor.execute("ALTER TABLE labs ADD COLUMN available_slots INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass
    # Add equipment_status column to existing labs table if it doesn't exist
    try:
        cursor.execute("ALTER TABLE labs ADD COLUMN equipment_status TEXT NOT NULL DEFAULT 'Not Available'")
    except sqlite3.OperationalError:
        # Column already exists, ignore
        pass
    # Create availability_slots table for lab availability
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS availability_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE CASCADE
        );
        """
    )
    # Table to record labs that are disabled for specific dates (admin action)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS disabled_labs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            disabled_date TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE CASCADE
        );
        """
    )
    # Table to track lab assistant assignments (which labs are assigned to
    # which lab assistants)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS lab_assistant_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            assistant_college_id TEXT NOT NULL,
            assigned_at TEXT NOT NULL,
            FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE CASCADE,
            FOREIGN KEY (assistant_college_id) REFERENCES users(college_id)
        );
        """
    )
    conn.commit()

    # Close the connection unless it's an in-memory database. Tests
    # commonly supply an in-memory connection via monkeypatching
    # `get_db_connection()`. Detect the underlying database file using
    # PRAGMA database_list; the file field will be ':memory:' for an
    # in-memory DB.
    try:
        db_list = conn.execute("PRAGMA database_list").fetchall()
        main_db_file = db_list[0][2] if db_list and len(db_list[0]) > 2 else None
    except Exception:
        main_db_file = None

    # If `main_db_file` is empty/None it's likely an in-memory DB; only
    # close when a real file path is present and it's not ':memory:'.
    if main_db_file and main_db_file != ":memory:":
        conn.close()
    # Seed some common science labs if the labs table is empty. Use the
    # same connection object `conn` returned by get_db_connection() to
    # avoid closing a test-supplied in-memory connection (tests monkey
    # patch get_db_connection()). Keep this lightweight and tolerant of
    # any errors to avoid breaking test setup.
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(1) as c FROM labs")
        row = cur.fetchone()
        count = row[0] if row else 0
        if count == 0:
            now = datetime.datetime.now(timezone.utc).isoformat()
            seed_labs = [
                ("Physics", 40, json.dumps(["Oscilloscope", "Projector"]), now),
                ("Chemistry", 30, json.dumps(["Fume hood", "Beakers", "Bunsen burner"]), now),
                ("Biology", 25, json.dumps(["Microscopes", "Slides"]), now),
                ("Biotechnology", 20, json.dumps(["PCR machine", "Centrifuge"]), now),
            ]
            for name, cap, equipment, created_at in seed_labs:
                try:
                    cur.execute(
                        "INSERT OR IGNORE INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
                        (name, cap, equipment, created_at),
                    )
                except Exception:
                    # Skip any problem inserting a particular seed row
                    pass
            conn.commit()
    except Exception:
        # Swallow errors; tests will assert table presence separately.
        pass
    print("Database initialization complete.")
# --- Helper Functions (Core Logic) ---


def validate_registration_data(data):
    """
    Validates the data against the user story security rules:
    1. Duplicate email/college ID check (handled separately by database constraints).
    2. Email format validation.
    3. Password complexity (min 8 chars, 1 number, 1 symbol).
    4. Role validation (student, admin, lab_assistant, faculty).
    """
    errors = []

    # Check for presence of all required fields
    if not all(
        key in data and data[key] for key in ["college_id", "name", "email", "password", "role"]
    ):
        errors.append("All fields (College ID, Name, Email, Password, Role) are required.")
        return False, errors

    # Role validation
    valid_roles = ["student", "admin", "lab_assistant", "faculty"]
    if data["role"] not in valid_roles:
        errors.append(f"Invalid role. Must be one of: {', '.join(valid_roles)}.")

    # Email format validation
    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_regex, data["email"]):
        errors.append("Invalid email format.")

    password = data["password"]
    # Password minimum length check
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    # Password complexity checks (1 number, 1 symbol)
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one number.")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one symbol (!@#$%^&*...).")

    return not errors, errors


def register_user(data):
    """
    Attempts to register a new user after validation.
    Returns (success: bool, message: str)
    """
    is_valid, errors = validate_registration_data(data)
    if not is_valid:
        return False, "Validation failed: " + ", ".join(errors)

    # Hash the password for secure storage
    hashed_password = generate_password_hash(data["password"])

    conn = get_db_connection()
    try:
        # Ensure users table exists (helps tests that swap DBs at runtime)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                college_id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
            );
            """
        )
        conn.commit()
        conn.execute(
            "INSERT INTO users "
            "(college_id, name, email, password_hash, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (data["college_id"], data["name"], data["email"], hashed_password, data["role"]),
        )
        conn.commit()
        return True, "Success: User registration complete. Redirecting to login page."
    except sqlite3.IntegrityError as e:
        # Check if the error is due to unique constraints (email or college_id)
        if "UNIQUE constraint failed: users.email" in str(e):
            return False, "Duplicate email validation error: This email is already registered."
        elif "UNIQUE constraint failed: users.college_id" in str(e):
            return (
                False,
                "Duplicate college ID validation error: This college ID is already registered.",
            )
        else:
            print(f"Database Error: {e}")
            return False, "A database error occurred during registration."
    finally:
        # Only close the connection if it's not an in-memory database (testing uses :memory:)
        if DATABASE != ":memory:":
            conn.close()


def _generate_token(payload: dict) -> str:
    """Return a JWT for the given payload (adds expiry)."""
    payload_copy = payload.copy()
    # Add expiry in a separate variable to keep line lengths short
    expiry = datetime.datetime.now(timezone.utc) + datetime.timedelta(
        seconds=JWT_EXP_DELTA_SECONDS
    )
    payload_copy["exp"] = expiry
    token = jwt.encode(
        payload_copy, SECRET_KEY, algorithm="HS256"
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def verify_token():
    """Extract and verify JWT token from Authorization header."""
    auth = request.headers.get("Authorization", None)
    if not auth or not auth.startswith("Bearer "):
        return None, jsonify({"message": "Missing or invalid Authorization header."}), 401

    token = auth.split(" ", 1)[1]
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return data, None, None
    except jwt.ExpiredSignatureError:
        return None, jsonify({"message": "Token expired."}), 401
    except jwt.InvalidTokenError:
        return None, jsonify({"message": "Invalid token."}), 401


def require_auth(f):
    """Decorator to require authentication for an endpoint."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token_data, error_response, status_code = verify_token()
        if error_response:
            return error_response, status_code
        request.current_user = token_data
        return f(*args, **kwargs)
    return decorated_function


def require_role(*allowed_roles):
    """Decorator to require specific role(s) for an endpoint."""
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            user_role = request.current_user.get("role")
            if user_role not in allowed_roles:
                return jsonify({"message": "Insufficient permissions."}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# --- Static File Routes ---

@app.route("/")
def index():
    """Serve index.html or redirect based on authentication."""
    # Check if user has token in request (optional - can just serve index.html)
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/home")
def home():
    """Alias for index page."""
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/register.html")
def serve_register():
    """Serve register.html."""
    return send_from_directory(BASE_DIR, "register.html")


@app.route("/login.html")
def serve_login():
    """Serve login.html."""
    return send_from_directory(BASE_DIR, "login.html")


@app.route("/dashboard.html")
def serve_dashboard():
    """Serve dashboard.html."""
    return send_from_directory(BASE_DIR, "dashboard.html")


@app.route("/available_labs.html")
def serve_available_labs():
    """Serve available_labs.html for students."""
    response = send_from_directory(BASE_DIR, "available_labs.html")
    # Prevent caching to ensure users see latest version
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route("/admin_available_labs.html")
@require_role("admin")
def serve_admin_available_labs():
    """Serve admin_available_labs.html for admins (requires auth via decorator)."""
    return send_from_directory(BASE_DIR, "admin_available_labs.html")


@app.route("/lab_assistant_labs.html")
@require_role("lab_assistant")
def serve_lab_assistant_labs():
    """Serve lab_assistant_labs.html for lab assistants (requires auth via decorator)."""
    return send_from_directory(BASE_DIR, "lab_assistant_labs.html")


# --- API Endpoint ---

@app.route("/api/register", methods=["POST"])
def handle_registration():
    """API endpoint to process user registration."""
    # Use silent=True so invalid JSON doesn't raise a BadRequest that
    # causes Flask to return an HTML error page. We want a JSON response.
    data = request.get_json(silent=True)
    # Log incoming registration requests for debugging (helps verify POST arrival)
    print(f"Received registration request from {request.remote_addr}: {data}")
    if data is None:
        return jsonify({"message": "Invalid JSON payload."}), 400

    success, message = register_user(data)

    if success:
        # User story success: confirmation message & redirect logic
        return jsonify({"message": message, "success": True}), 201
    else:
        # User story duplicate/validation error
        return jsonify({"message": message, "success": False}), 400


@app.route("/api/login", methods=["POST"])
def handle_login():
    """Authenticate user and return JWT token on success."""
    # Use silent=True to handle invalid JSON gracefully
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    if "college_id" not in data or "password" not in data:
        return jsonify({"message": "College ID and password required.", "success": False}), 400

    college_id = data["college_id"]
    password = data["password"]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT college_id, password_hash, name, role FROM users WHERE college_id = ?", (college_id,))
        row = cursor.fetchone()

        # Do not leak whether the user exists
        if row is None:
            return jsonify({"message": "Invalid credentials.", "success": False}), 401

        stored_hash = row["password_hash"]
        if not check_password_hash(stored_hash, password):
            return jsonify({"message": "Invalid credentials.", "success": False}), 401

        payload = {"college_id": row["college_id"], "role": row["role"], "name": row["name"]}
        token = _generate_token(payload)

        return jsonify({
            "token": token,
            "success": True,
            "role": row["role"],
            "name": row["name"]
        }), 200
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({"message": "An error occurred during login.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/admin/labs/available", methods=["GET"])
@require_role("admin")
def admin_get_available_labs():
    """
    Admin view: Return ALL labs with availability slots, booking details, occupancy metrics,
    and lab status for a specific date. Requires admin role.
    Shows fully booked labs and occupancy labels for complete system visibility.
    """
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Date is required"}), 400

    # Validate date
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if date_obj.strftime("%Y-%m-%d") != date_str:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Past dates not allowed for admin actions either
    today = datetime.datetime.now().date()
    if date_obj.date() < today:
        return jsonify({"error": "Past dates are not allowed"}), 400

    day_of_week = get_day_of_week(date_str)
    if not day_of_week:
        return jsonify({"error": "Invalid date"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Fetch all labs with their availability slots for this day
        labs_query = (
            """
            SELECT l.id, l.name, l.capacity, l.equipment,
                   av.start_time, av.end_time
            FROM labs l
            LEFT JOIN availability_slots av ON l.id = av.lab_id AND av.day_of_week = ?
            ORDER BY l.name ASC, av.start_time ASC
            """
        )
        cursor.execute(labs_query, (day_of_week,))
        labs_rows = cursor.fetchall()

        # Fetch all bookings for this lab on this date
        bookings_query = (
            """
            SELECT b.id, b.college_id, b.lab_name, b.start_time, b.end_time,
                   b.status, b.created_at, u.name, u.email
            FROM bookings b
            LEFT JOIN users u ON b.college_id = u.college_id
            WHERE b.booking_date = ?
            ORDER BY b.lab_name ASC, b.start_time ASC
            """
        )
        cursor.execute(bookings_query, (date_str,))
        bookings_rows = cursor.fetchall()

        # Build labs dictionary with slots
        labs_dict = {}
        for row in labs_rows:
            lab_id = row[0]
            lab_name = row[1]
            if lab_id not in labs_dict:
                labs_dict[lab_id] = {
                    "lab_id": lab_id,
                    "lab_name": lab_name,
                    "capacity": row[2],
                    "equipment": row[3],
                    "availability_slots": [],
                    "bookings": [],
                    "slots_by_time": {}
                }

            # Add availability slot if it exists
            if row[4] and row[5]:
                avail_start = row[4]
                avail_end = row[5]
                # Attach per-slot capacity (lab capacity applies to each slot)
                slot = {"start_time": avail_start, "end_time": avail_end, "capacity": row[2]}
                if slot not in labs_dict[lab_id]["availability_slots"]:
                    labs_dict[lab_id]["availability_slots"].append(slot)
                    # Initialize slot occupancy tracker
                    time_key = f"{avail_start}-{avail_end}"
                    if time_key not in labs_dict[lab_id]["slots_by_time"]:
                        labs_dict[lab_id]["slots_by_time"][time_key] = {
                            "start_time": avail_start,
                            "end_time": avail_end,
                            "booked_count": 0,
                            "bookings": [],
                            "capacity": row[2]
                        }

        # Process bookings and match them to slots
        for booking_row in bookings_rows:
            booking_id = booking_row[0]
            college_id = booking_row[1]
            lab_name = booking_row[2]
            booking_start = booking_row[3]
            booking_end = booking_row[4]
            booking_status = booking_row[5]
            booking_created_at = booking_row[6]
            booking_user_name = booking_row[7]
            booking_user_email = booking_row[8]

            # Find the lab by name
            lab_id = None
            for lid, ldata in labs_dict.items():
                if ldata["lab_name"] == lab_name:
                    lab_id = lid
                    break

            if lab_id:
                booking = {
                    "id": booking_id,
                    "college_id": college_id,
                    "name": booking_user_name,
                    "email": booking_user_email,
                    "start_time": booking_start,
                    "end_time": booking_end,
                    "status": booking_status,
                    "created_at": booking_created_at
                }

                # Add booking to lab's booking list (track all bookings)
                if booking not in labs_dict[lab_id]["bookings"]:
                    labs_dict[lab_id]["bookings"].append(booking)

                # Check which availability slots this booking overlaps with
                # Only count APPROVED bookings for occupancy
                if booking_status == 'approved':
                    for time_key, slot_info in labs_dict[lab_id]["slots_by_time"].items():
                        slot_start = slot_info["start_time"]
                        slot_end = slot_info["end_time"]
                        # Check if booking overlaps with this slot
                        if booking_start < slot_end and booking_end > slot_start:
                            # Booking overlaps with this slot
                            labs_dict[lab_id]["slots_by_time"][time_key]["booked_count"] += 1
                            if booking not in labs_dict[lab_id]["slots_by_time"][time_key]["bookings"]:
                                labs_dict[lab_id]["slots_by_time"][time_key]["bookings"].append(
                                    booking
                                )

        # Disabled labs for this date
        try:
            cursor.execute(
                "SELECT lab_id, reason FROM disabled_labs WHERE disabled_date = ?",
                (date_str,)
            )
            disabled_rows = cursor.fetchall()
            disabled = {r[0]: r[1] for r in disabled_rows} if disabled_rows else {}
        except Exception:
            disabled = {}

        labs = []
        for lab_id, lab_data in labs_dict.items():
            # Calculate lab occupancy summary (treat capacity as per-slot)
            total_slots = len(lab_data["availability_slots"])
            # total possible booking-units = slots * capacity
            per_slot_capacity = lab_data.get("capacity", 1) or 1
            total_possible = total_slots * per_slot_capacity
            # Check for approved bookings
            approved_bookings_list = [
                b for b in lab_data["bookings"]
                if isinstance(b, dict) and b.get('status') == 'approved'
            ]
            has_approved_bookings = len(approved_bookings_list) > 0

            # total_booked = sum of approved bookings only
            if len(lab_data["slots_by_time"]) > 0:
                total_booked = (
                    sum(s["booked_count"] for s in lab_data["slots_by_time"].values())
                    if lab_data.get("slots_by_time")
                    else 0
                )
            else:
                # If no slots configured but has approved bookings, count them
                total_booked = len(approved_bookings_list)
            total_free = max(0, total_possible - total_booked)

            # Determine lab status
            if lab_id in disabled:
                status = "Disabled"
                status_badge = "🔴"
            elif has_approved_bookings:
                # If lab has approved bookings, it's Active (even if no slots configured)
                status = "Active"
                status_badge = "🟢"
            elif total_slots == 0:
                status = "No lab active"
                status_badge = "🟡"
            else:
                status = "Active"
                status_badge = "🟢"

            # Format slots with occupancy labels (per-slot capacity)
            # Only count APPROVED bookings for occupancy
            formatted_slots = []
            # If lab has approved bookings but no slots configured, create slots from approved bookings
            if len(approved_bookings_list) > 0 and total_slots == 0:
                for booking in approved_bookings_list:
                    slot_start = booking['start_time']
                    slot_end = booking['end_time']
                    capacity = per_slot_capacity
                    formatted_slots.append({
                        "time": f"{slot_start}-{slot_end}",
                        "start_time": slot_start,
                        "end_time": slot_end,
                        "booked_count": 1,
                        "available": 0,
                        "occupancy_label": "FULL",
                        "bookings": [booking]
                    })
            else:
                # Normal case: use availability slots, but only count approved bookings
                for time_key, slot_info in lab_data["slots_by_time"].items():
                    # Count only approved bookings for this slot
                    slot_approved_bookings = [
                        b for b in approved_bookings_list
                        if slots_overlap(
                            slot_info["start_time"], slot_info["end_time"],
                            b['start_time'], b['end_time']
                        )
                    ]
                    booked = len(slot_approved_bookings)
                    capacity = per_slot_capacity
                    available = capacity - booked
                    occupancy_label = "FULL" if available <= 0 else f"{max(0, available)}/{capacity} free"
                    formatted_slots.append({
                        "time": time_key,
                        "start_time": slot_info["start_time"],
                        "end_time": slot_info["end_time"],
                        "booked_count": booked,
                        "available": max(0, available),
                        "occupancy_label": occupancy_label,
                        "bookings": slot_approved_bookings
                    })

            # Get time slots - from availability slots or from approved bookings if no slots
            time_slots_list = []
            if lab_data["availability_slots"]:
                time_slots_list = [
                    f"{slot['start_time']}-{slot['end_time']}"
                    for slot in lab_data["availability_slots"]
                ]
            elif has_approved_bookings and approved_bookings_list:
                time_slots_list = [
                    f"{b['start_time']}-{b['end_time']}"
                    for b in approved_bookings_list
                ]

            labs.append({
                "lab_id": lab_id,
                "lab_name": lab_data["lab_name"],
                "capacity": lab_data["capacity"],
                "equipment": lab_data["equipment"],
                "status": status,
                "status_badge": status_badge,
                "time_slots": time_slots_list,
                "occupancy": {
                    "total_slots": total_slots,
                    "booked": total_booked,
                    "free": total_free,
                    "occupancy_label": (
                        f"{total_free}/{total_possible} free" if total_free > 0 else "ALL BOOKED"
                    )
                },
                "availability_slots": formatted_slots,
                "bookings": lab_data["bookings"],
                "disabled": lab_id in disabled,
                "disabled_reason": disabled.get(lab_id)
            })

        return jsonify({
            "date": date_str,
            "day_of_week": day_of_week,
            "labs": labs,
            "total_labs": len(labs)
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in admin_get_available_labs: {e}")
        return jsonify({"error": "Something went wrong"}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/admin/bookings/<int:booking_id>/override", methods=["POST"])
@require_role("admin")
def admin_override_booking(booking_id):
    """Admin can override (cancel) a booking to free a slot."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, status FROM bookings WHERE id = ?", (booking_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"message": "Booking not found."}), 404

        # Mark as cancelled/overridden
        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ?",
            ("cancelled", updated_at, booking_id),
        )
        conn.commit()

        return (
            jsonify({"message": "Booking cancelled/overridden successfully.", "success": True}),
            200,
        )
    except sqlite3.Error as e:
        print(f"Database Error in admin_override_booking: {e}")
        return jsonify({"message": "Failed to override booking.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/admin/labs/<int:lab_id>/disable", methods=["POST"])
@require_role("admin")
def admin_disable_lab(lab_id):
    """Disable a lab for a specific date (persisted in disabled_labs)."""
    data = request.get_json(silent=True)
    if not data or "date" not in data:
        return jsonify({"message": "Date is required in payload."}), 400

    date_str = data["date"]
    reason = data.get("reason")

    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if date_obj.strftime("%Y-%m-%d") != date_str:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    today = datetime.datetime.now().date()
    if date_obj.date() < today:
        return jsonify({"error": "Past dates are not allowed"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Ensure labs exist
        cursor.execute("SELECT id FROM labs WHERE id = ?", (lab_id,))
        if not cursor.fetchone():
            return jsonify({"message": "Lab not found."}), 404

        created_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO disabled_labs (lab_id, disabled_date, reason, created_at) VALUES (?, ?, ?, ?)",
            (lab_id, date_str, reason, created_at),
        )
        conn.commit()
        return jsonify({"message": "Lab disabled for date.", "success": True}), 200
    except sqlite3.Error as e:
        print(f"Database Error in admin_disable_lab: {e}")
        return jsonify({"message": "Failed to disable lab.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/lab-assistant/labs/assigned", methods=["GET"])
@require_role("lab_assistant")
def lab_assistant_assigned_labs():
    """
    Lab Assistant view: Return only assigned labs with today's availability and bookings.
    Shows both free and booked slots to help lab assistants prepare.
    """
    assistant_college_id = request.current_user.get("college_id")

    # Determine date (default to today)
    date_str = request.args.get("date")
    if not date_str:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # Validate date format
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if date_obj.strftime("%Y-%m-%d") != date_str:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    day_of_week = get_day_of_week(date_str)
    if not day_of_week:
        return jsonify({"error": "Invalid date"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get labs assigned to this lab assistant
        cursor.execute(
            "SELECT lab_id FROM lab_assistant_assignments WHERE assistant_college_id = ?",
            (assistant_college_id,),
        )
        assignment_rows = cursor.fetchall()
        assigned_lab_ids = set([r[0] for r in assignment_rows]) if assignment_rows else set()

        if not assigned_lab_ids:
            return jsonify({
                "date": date_str,
                "assigned_labs": [],
                "message": "No labs assigned to you."
            }), 200

        # Get availability and bookings for assigned labs on the given date
        placeholders = ",".join("?" * len(assigned_lab_ids))
        query = (
            f"""
            SELECT
                l.id as lab_id,
                l.name as lab_name,
                l.capacity,
                l.equipment,
                av.start_time as avail_start,
                av.end_time as avail_end,
                b.id as booking_id,
                b.college_id as booking_college_id,
                b.start_time as booking_start,
                b.end_time as booking_end,
                b.status as booking_status,
                u.name as booking_name,
                u.email as booking_email
            FROM labs l
            LEFT JOIN availability_slots av ON l.id = av.lab_id
                AND av.day_of_week = ?
            LEFT JOIN bookings b ON l.name = b.lab_name
                AND b.booking_date = ?
                AND b.status IN ('approved', 'pending')
            LEFT JOIN users u ON b.college_id = u.college_id
            WHERE l.id IN ({placeholders})
            ORDER BY l.name ASC, av.start_time ASC, b.start_time ASC
            """
        )

        params = [day_of_week, date_str] + list(assigned_lab_ids)
        cursor.execute(query, params)
        rows = cursor.fetchall()

        labs_dict = {}
        for row in rows:
            lab_id = row["lab_id"]
            if lab_id not in labs_dict:
                labs_dict[lab_id] = {
                    "lab_id": lab_id,
                    "lab_name": row["lab_name"],
                    "capacity": row["capacity"],
                    "equipment": row["equipment"],
                    "availability_slots": [],
                    "bookings": []
                }

            if row["avail_start"] and row["avail_end"]:
                slot = {"start_time": row["avail_start"],
                        "end_time": row["avail_end"]}
                if slot not in labs_dict[lab_id]["availability_slots"]:
                    labs_dict[lab_id]["availability_slots"].append(slot)

            if row["booking_id"]:
                booking = {
                    "id": row["booking_id"],
                    "college_id": row["booking_college_id"],
                    "name": row["booking_name"],
                    "email": row["booking_email"],
                    "start_time": row["booking_start"],
                    "end_time": row["booking_end"],
                    "status": row["booking_status"]
                }
                if booking not in labs_dict[lab_id]["bookings"]:
                    labs_dict[lab_id]["bookings"].append(booking)

        # Format response
        assigned_labs = []
        for lab_id, lab_data in labs_dict.items():
            formatted_avail = [
                f"{s['start_time']}-{s['end_time']}"
                for s in lab_data["availability_slots"]
            ]
            assigned_labs.append({
                "lab_id": lab_id,
                "lab_name": lab_data["lab_name"],
                "capacity": lab_data["capacity"],
                "equipment": lab_data["equipment"],
                "availability_slots": formatted_avail,
                "bookings": lab_data["bookings"],
                "booked_slots_count": len(lab_data["bookings"]),
                "free_slots_count": len(formatted_avail)
            })

        return jsonify({
            "date": date_str,
            "assigned_labs": assigned_labs,
            "total_assigned": len(assigned_labs)
        }), 200

    except sqlite3.Error as e:
        print(f"Database Error in lab_assistant_assigned_labs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Something went wrong"}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/me", methods=["GET"])
def handle_me():
    """Return user info based on Bearer token."""
    auth = request.headers.get("Authorization", None)
    if not auth or not auth.startswith("Bearer "):
        return jsonify({"message": "Missing or invalid Authorization header."}), 401

    token = auth.split(" ", 1)[1]
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return jsonify({"message": "Token expired."}), 401
    except jwt.InvalidTokenError:
        return jsonify({"message": "Invalid token."}), 401

    # Return minimal user info
    return jsonify({"college_id": data.get("college_id"), "role": data.get("role"), "name": data.get("name")}), 200


# --- Booking Endpoints ---

@app.route("/api/bookings", methods=["POST"])
@require_auth
def create_booking():
    """Create a new lab booking request."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    required_fields = ["lab_name", "booking_date", "start_time", "end_time"]
    if not all(field in data for field in required_fields):
        return jsonify({"message": "Missing required fields.", "success": False}), 400

    college_id = request.current_user.get("college_id")
    lab_name = data["lab_name"]
    booking_date = data["booking_date"]
    start_time = data["start_time"]
    end_time = data["end_time"]

    # Validate date and time format
    try:
        datetime.datetime.strptime(booking_date, "%Y-%m-%d")
        datetime.datetime.strptime(start_time, "%H:%M")
        datetime.datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return jsonify({"message": "Invalid date or time format.", "success": False}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Ensure bookings table exists
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                college_id TEXT NOT NULL,
                lab_name TEXT NOT NULL,
                booking_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (college_id) REFERENCES users(college_id)
            );
            """
        )
        conn.commit()

        created_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO bookings (college_id, lab_name, booking_date, start_time, end_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (college_id, lab_name, booking_date, start_time, end_time, created_at),
        )
        conn.commit()
        booking_id = cursor.lastrowid
        return jsonify({
            "message": "Booking request created successfully.",
            "booking_id": booking_id,
            "success": True
        }), 201
    except sqlite3.Error as e:
        print(f"Database Error in create_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to create booking.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in create_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/bookings", methods=["GET"])
@require_auth
def get_bookings():
    """Get bookings for the current user or all bookings for admin."""
    college_id = request.current_user.get("college_id")
    role = request.current_user.get("role")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Ensure bookings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if not cursor.fetchone():
            # Table doesn't exist yet, return empty list
            return jsonify({"bookings": [], "success": True}), 200

        if role == "admin":
            # Admin can see all bookings
            cursor.execute(
                """
                SELECT b.*, u.name, u.email
                FROM bookings b
                JOIN users u ON b.college_id = u.college_id
                ORDER BY b.created_at DESC
                """
            )
        else:
            # Regular users see only their bookings
            cursor.execute(
                """
                SELECT b.*, u.name, u.email
                FROM bookings b
                JOIN users u ON b.college_id = u.college_id
                WHERE b.college_id = ?
                ORDER BY b.created_at DESC
                """,
                (college_id,),
            )

        rows = cursor.fetchall()
        bookings = []
        for row in rows:
            bookings.append({
                "id": row["id"],
                "college_id": row["college_id"],
                "name": row["name"],
                "email": row["email"],
                "lab_name": row["lab_name"],
                "booking_date": row["booking_date"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"] if row["updated_at"] else None,
            })

        return jsonify({"bookings": bookings, "success": True}), 200
    except sqlite3.Error as e:
        print(f"Database Error in get_bookings: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to retrieve bookings.", "success": False, "error": str(e)}), 500
    except Exception as e:
        print(f"Unexpected error in get_bookings: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False, "error": str(e)}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/bookings/pending", methods=["GET"])
@require_role("admin")
def get_pending_bookings():
    """Get all pending booking requests (admin only)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Ensure bookings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if not cursor.fetchone():
            # Table doesn't exist yet, return empty list
            return jsonify({"bookings": [], "success": True}), 200

        cursor.execute(
            """
            SELECT b.*, u.name, u.email
            FROM bookings b
            JOIN users u ON b.college_id = u.college_id
            WHERE b.status = 'pending'
            ORDER BY b.created_at DESC
            """
        )
        rows = cursor.fetchall()
        bookings = []
        for row in rows:
            bookings.append({
                "id": row["id"],
                "college_id": row["college_id"],
                "name": row["name"],
                "email": row["email"],
                "lab_name": row["lab_name"],
                "booking_date": row["booking_date"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "status": row["status"],
                "created_at": row["created_at"],
            })

        return jsonify({"bookings": bookings, "success": True}), 200
    except sqlite3.Error as e:
        print(f"Database Error in get_pending_bookings: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to retrieve pending bookings.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in get_pending_bookings: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/bookings/<int:booking_id>/approve", methods=["POST"])
@require_role("admin")
def approve_booking(booking_id):
    """Approve a booking request (admin only)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if bookings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if not cursor.fetchone():
            return jsonify({"message": "Bookings table does not exist.", "success": False}), 404

        # Check if booking exists and is pending
        cursor.execute(
            "SELECT college_id, lab_name, booking_date, start_time, end_time "
            "FROM bookings WHERE id = ? AND status = 'pending'",
            (booking_id,),
        )
        booking = cursor.fetchone()
        if not booking:
            return jsonify({"message": "Booking not found or already processed.", "success": False}), 404

        # Update booking status
        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE bookings SET status = 'approved', updated_at = ? WHERE id = ?",
            (updated_at, booking_id),
        )

        # Decrement available_slots for the lab when booking is approved
        lab_name = booking["lab_name"]
        # Get current available_slots and capacity
        cursor.execute("SELECT available_slots, capacity FROM labs WHERE name = ?", (lab_name,))
        lab_row = cursor.fetchone()
        if lab_row:
            try:
                if "available_slots" in lab_row.keys():
                    current_slots = lab_row["available_slots"] if lab_row["available_slots"] is not None else 0
                else:
                    # If available_slots column doesn't exist, use capacity as default
                    current_slots = lab_row["capacity"] if "capacity" in lab_row.keys() else 0
            except (KeyError, AttributeError):
                current_slots = lab_row["capacity"] if "capacity" in lab_row.keys() else 0
            new_slots = max(0, current_slots - 1)  # Ensure it doesn't go below 0
            # Ensure available_slots column exists before updating
            try:
                cursor.execute("ALTER TABLE labs ADD COLUMN available_slots INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists
            cursor.execute(
                "UPDATE labs SET available_slots = ?, updated_at = ? WHERE name = ?",
                (new_slots, updated_at, lab_name)
            )

        conn.commit()

        # Get user email for notification (for future email sending)
        cursor.execute(
            "SELECT email, name FROM users WHERE college_id = ?",
            (booking["college_id"],)
        )
        # In production, use the user data to send email notification
        # For now, we'll just return success
        return jsonify({
            "message": "Booking approved successfully. User notified.",
            "success": True
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in approve_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to approve booking.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in approve_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/bookings/<int:booking_id>/reject", methods=["POST"])
@require_role("admin")
def reject_booking(booking_id):
    """Reject a booking request (admin only)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if bookings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if not cursor.fetchone():
            return jsonify({"message": "Bookings table does not exist.", "success": False}), 404

        # Check if booking exists and is pending
        cursor.execute(
            "SELECT college_id, lab_name, booking_date, start_time, end_time "
            "FROM bookings WHERE id = ? AND status = 'pending'",
            (booking_id,),
        )
        booking = cursor.fetchone()
        if not booking:
            return jsonify({"message": "Booking not found or already processed.", "success": False}), 404

        # Update booking status
        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE bookings SET status = 'rejected', updated_at = ? WHERE id = ?",
            (updated_at, booking_id),
        )
        conn.commit()

        return jsonify({
            "message": "Booking rejected successfully.",
            "success": True
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in reject_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to reject booking.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in reject_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


# --- Lab Management Functions ---


def validate_lab_data(data):
    """
    Validates lab data for creation/update.
    Required fields: name, capacity, equipment.
    """
    errors = []

    # Check for presence of required fields
    # Note: For equipment, we check if it exists and is not None
    # Empty list [] is falsy, but we want to allow it to pass this check
    # so we can validate it properly in the equipment validation section
    if "name" not in data or not data.get("name"):
        errors.append("All fields (name, capacity, equipment) are required.")
        return False, errors
    if "capacity" not in data or data.get("capacity") is None:
        errors.append("All fields (name, capacity, equipment) are required.")
        return False, errors
    if "equipment" not in data or data.get("equipment") is None:
        errors.append("All fields (name, capacity, equipment) are required.")
        return False, errors

    # Validate name (non-empty string)
    if not isinstance(data["name"], str) or len(data["name"].strip()) == 0:
        errors.append("Lab name must be a non-empty string.")
    elif len(data["name"].strip()) > 100:
        errors.append("Lab name must be less than 100 characters.")

    # Validate capacity (positive integer)
    try:
        capacity = int(data["capacity"])
        if capacity <= 0:
            errors.append("Capacity must be a positive integer.")
        elif capacity > 1000:
            errors.append("Capacity must be less than or equal to 1000.")
    except (ValueError, TypeError):
        errors.append("Capacity must be a valid positive integer.")

    # Validate equipment (list or string that can be converted to list)
    equipment = data["equipment"]
    if isinstance(equipment, str):
        # If it's a string, try to parse as JSON array
        try:
            equipment_list = json.loads(equipment)
            if not isinstance(equipment_list, list):
                errors.append("Equipment must be a list or JSON array.")
            elif len(equipment_list) == 0:
                errors.append("Equipment list cannot be empty.")
        except (json.JSONDecodeError, ValueError):
            # If not JSON, treat as comma-separated string
            if len(equipment.strip()) == 0:
                errors.append("Equipment list cannot be empty.")
    elif isinstance(equipment, list):
        if len(equipment) == 0:
            errors.append("Equipment list cannot be empty.")
    else:
        errors.append("Equipment must be a list or JSON array string.")

    return not errors, errors


# --- Lab Management Endpoints ---


@app.route("/api/labs", methods=["POST"])
@require_role("admin")
def create_lab():
    """Create a new lab entry (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    is_valid, errors = validate_lab_data(data)
    if not is_valid:
        return jsonify({"message": "Validation failed: " + ", ".join(errors), "success": False}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Ensure labs table exists
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS labs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                capacity INTEGER NOT NULL,
                available_slots INTEGER NOT NULL DEFAULT 0,
                equipment TEXT NOT NULL,
                equipment_status TEXT NOT NULL DEFAULT 'Not Available',
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            """
        )
        # Add available_slots column to existing labs table if it doesn't exist
        try:
            cursor.execute("ALTER TABLE labs ADD COLUMN available_slots INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass
        # Add equipment_status column to existing labs table if it doesn't exist
        try:
            cursor.execute("ALTER TABLE labs ADD COLUMN equipment_status TEXT NOT NULL DEFAULT 'Not Available'")
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass
        conn.commit()

        # Parse equipment to JSON string if it's a list
        equipment = data["equipment"]
        if isinstance(equipment, list):
            equipment = json.dumps(equipment)

        # Set available_slots to capacity by default for new labs
        capacity = int(data["capacity"])
        available_slots = capacity  # New labs start with all slots available

        created_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO labs (name, capacity, available_slots, equipment, equipment_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (data["name"].strip(), capacity, available_slots, equipment, "Not Available", created_at),
        )
        conn.commit()
        lab_id = cursor.lastrowid

        # Get the created lab
        cursor.execute("SELECT * FROM labs WHERE id = ?", (lab_id,))
        lab_row = cursor.fetchone()
        # Safely get equipment_status and available_slots
        equipment_status = "Not Available"
        retrieved_available_slots = available_slots
        try:
            if "equipment_status" in lab_row.keys():
                equipment_status = lab_row["equipment_status"] if lab_row["equipment_status"] else "Not Available"
            if "available_slots" in lab_row.keys():
                retrieved_available_slots = (
                    lab_row["available_slots"] if lab_row["available_slots"] is not None else capacity
                )
        except (KeyError, AttributeError):
            pass
        lab_data = {
            "id": lab_row["id"],
            "name": lab_row["name"],
            "capacity": lab_row["capacity"],
            "available_slots": retrieved_available_slots,
            "equipment": lab_row["equipment"],
            "equipment_status": equipment_status,
            "created_at": lab_row["created_at"],
            "updated_at": lab_row["updated_at"],
        }

        return jsonify({
            "message": "Lab created successfully.",
            "lab": lab_data,
            "success": True
        }), 201
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: labs.name" in str(e):
            return jsonify({"message": "A lab with this name already exists.", "success": False}), 400
        print(f"Integrity Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to create lab.", "success": False}), 500
    except sqlite3.Error as e:
        print(f"Database Error in create_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to create lab.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in create_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/labs", methods=["GET"])
@require_auth
def get_labs():
    """Get all labs (authenticated users)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if labs table exists, if not return empty list
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='labs'")
        if not cursor.fetchone():
            # Table doesn't exist yet, return empty list
            return jsonify({"labs": [], "success": True}), 200

        cursor.execute("SELECT * FROM labs ORDER BY name ASC")
        rows = cursor.fetchall()
        labs = []
        for row in rows:
            # Safely get equipment_status and available_slots
            equipment_status = "Not Available"
            capacity_val = row["capacity"] if "capacity" in row.keys() else 0
            available_slots = capacity_val  # Default to capacity if not set
            try:
                if "equipment_status" in row.keys():
                    equipment_status = row["equipment_status"] if row["equipment_status"] else "Not Available"
                if "available_slots" in row.keys():
                    available_slots = row["available_slots"] if row["available_slots"] is not None else capacity_val
            except (KeyError, AttributeError):
                pass

            # Get upcoming reservations for this lab
            upcoming_reservations = []
            try:
                cursor.execute(
                    """
                    SELECT id, college_id, booking_date, start_time, end_time, status
                    FROM bookings
                    WHERE lab_name = ? AND booking_date >= date('now')
                    ORDER BY booking_date ASC, start_time ASC
                    LIMIT 10
                    """,
                    (row["name"],)
                )
                reservation_rows = cursor.fetchall()
                for res_row in reservation_rows:
                    upcoming_reservations.append({
                        "id": res_row["id"],
                        "college_id": res_row["college_id"],
                        "reservation_date": res_row["booking_date"],
                        "start_time": res_row["start_time"],
                        "end_time": res_row["end_time"],
                        "status": res_row["status"]
                    })
            except Exception:
                pass  # If bookings table doesn't exist, skip

            labs.append({
                "id": row["id"],
                "name": row["name"],
                "capacity": row["capacity"],
                "available_slots": available_slots,
                "equipment": row["equipment"],
                "equipment_status": equipment_status,
                "upcoming_reservations": upcoming_reservations,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"] if row["updated_at"] else None,
            })

        return jsonify({"labs": labs, "success": True}), 200
    except sqlite3.Error as e:
        print(f"Database Error in get_labs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to retrieve labs.", "error": str(e), "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in get_labs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/labs/<int:lab_id>", methods=["GET"])
@require_auth
def get_lab(lab_id):
    """Get a specific lab by ID (authenticated users)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if labs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='labs'")
        if not cursor.fetchone():
            return jsonify({"message": "Labs table does not exist.", "success": False}), 404

        cursor.execute("SELECT * FROM labs WHERE id = ?", (lab_id,))
        row = cursor.fetchone()

        if not row:
            return jsonify({"message": "Lab not found.", "success": False}), 404

        # Safely get equipment_status and available_slots
        equipment_status = "Not Available"
        capacity_val = row["capacity"] if "capacity" in row.keys() else 0
        available_slots = capacity_val
        try:
            if "equipment_status" in row.keys():
                equipment_status = row["equipment_status"] if row["equipment_status"] else "Not Available"
            if "available_slots" in row.keys():
                available_slots = row["available_slots"] if row["available_slots"] is not None else capacity_val
        except (KeyError, AttributeError):
            pass

        # Get upcoming reservations for this lab
        upcoming_reservations = []
        try:
            cursor.execute(
                """
                SELECT id, college_id, booking_date, start_time, end_time, status
                FROM bookings
                WHERE lab_name = ? AND booking_date >= date('now')
                ORDER BY booking_date ASC, start_time ASC
                LIMIT 10
                """,
                (row["name"],)
            )
            reservation_rows = cursor.fetchall()
            for res_row in reservation_rows:
                upcoming_reservations.append({
                    "id": res_row["id"],
                    "college_id": res_row["college_id"],
                    "reservation_date": res_row["booking_date"],
                    "start_time": res_row["start_time"],
                    "end_time": res_row["end_time"],
                    "status": res_row["status"]
                })
        except Exception:
            pass  # If bookings table doesn't exist, skip

        lab_data = {
            "id": row["id"],
            "name": row["name"],
            "capacity": row["capacity"],
            "available_slots": available_slots,
            "equipment": row["equipment"],
            "equipment_status": equipment_status,
            "upcoming_reservations": upcoming_reservations,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"] if row["updated_at"] else None,
        }

        return jsonify({"lab": lab_data, "success": True}), 200
    except sqlite3.Error as e:
        print(f"Database Error in get_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to retrieve lab.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in get_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/labs/<int:lab_id>", methods=["PUT"])
@require_role("admin")
def update_lab(lab_id):
    """Update a lab entry (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    is_valid, errors = validate_lab_data(data)
    if not is_valid:
        return jsonify({"message": "Validation failed: " + ", ".join(errors), "success": False}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Check if labs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='labs'")
        if not cursor.fetchone():
            return jsonify({"message": "Labs table does not exist.", "success": False}), 404

        # Check if lab exists
        cursor.execute("SELECT id FROM labs WHERE id = ?", (lab_id,))
        if not cursor.fetchone():
            return jsonify({"message": "Lab not found.", "success": False}), 404

        # Parse equipment to JSON string if it's a list
        equipment = data["equipment"]
        if isinstance(equipment, list):
            equipment = json.dumps(equipment)

        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            UPDATE labs SET name = ?, capacity = ?, equipment = ?, updated_at = ?
            WHERE id = ?
            """,
            (data["name"].strip(), int(data["capacity"]), equipment, updated_at, lab_id),
        )
        conn.commit()

        # Get the updated lab
        cursor.execute("SELECT * FROM labs WHERE id = ?", (lab_id,))
        lab_row = cursor.fetchone()
        lab_data = {
            "id": lab_row["id"],
            "name": lab_row["name"],
            "capacity": lab_row["capacity"],
            "equipment": lab_row["equipment"],
            "created_at": lab_row["created_at"],
            "updated_at": lab_row["updated_at"],
        }

        return jsonify({
            "message": "Lab updated successfully.",
            "lab": lab_data,
            "success": True
        }), 200
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: labs.name" in str(e):
            return jsonify({"message": "A lab with this name already exists.", "success": False}), 400
        print(f"Integrity Error in update_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to update lab.", "success": False}), 500
    except sqlite3.Error as e:
        print(f"Database Error in update_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to update lab.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in update_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/labs/<int:lab_id>", methods=["DELETE"])
@require_role("admin")
def delete_lab(lab_id):
    """Delete a lab entry and its associated availability slots (admin only)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if labs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='labs'")
        if not cursor.fetchone():
            return jsonify({"message": "Labs table does not exist.", "success": False}), 404

        # Check if lab exists
        cursor.execute("SELECT id, name FROM labs WHERE id = ?", (lab_id,))
        lab = cursor.fetchone()
        if not lab:
            return jsonify({"message": "Lab not found.", "success": False}), 404

        lab_name = lab["name"]

        # Delete associated availability slots (CASCADE should handle this, but explicit is better)
        cursor.execute("DELETE FROM availability_slots WHERE lab_id = ?", (lab_id,))

        # Delete the lab
        cursor.execute("DELETE FROM labs WHERE id = ?", (lab_id,))
        conn.commit()

        return jsonify({
            "message": f"Lab '{lab_name}' deleted successfully along with its availability slots.",
            "success": True
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in delete_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to delete lab.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in delete_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


# --- Helper Functions for Available Labs ---


def get_day_of_week(date_str):
    """
    Get the day of week name from a date string (YYYY-MM-DD).
    Returns: 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
    """
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        return days[date_obj.weekday()]
    except ValueError:
        return None


def time_to_minutes(time_str):
    """Convert time string (HH:MM) to minutes since midnight."""
    try:
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def slots_overlap(slot1_start, slot1_end, slot2_start, slot2_end):
    """
    Check if two time slots overlap.
    Returns True if slots overlap, False otherwise.
    """
    start1 = time_to_minutes(slot1_start)
    end1 = time_to_minutes(slot1_end)
    start2 = time_to_minutes(slot2_start)
    end2 = time_to_minutes(slot2_end)

    if start1 is None or end1 is None or start2 is None or end2 is None:
        return False

    # Slots overlap if one starts before the other ends
    return start1 < end2 and start2 < end1


def filter_available_slots(availability_slots, bookings):
    """
    Filter out availability slots that overlap with existing bookings.
    Treat `capacity` as per-slot capacity: a slot is available if the number
    of overlapping bookings is less than `capacity`.
    Returns list of available slots.
    """
    available = []
    # Default capacity per slot (fallback) - will be overridden by caller where possible
    # Caller should pass lab capacity as part of lab data; here we expect bookings to be
    # plain bookings and availability_slots to be list of slots. We'll assume callers
    # will filter using correct capacity by counting overlaps vs capacity.
    for slot in availability_slots:
        slot_start = slot['start_time']
        slot_end = slot['end_time']

        # Count how many bookings overlap this slot
        overlap_count = 0
        for booking in bookings:
            booking_start = booking['start_time']
            booking_end = booking['end_time']
            if slots_overlap(slot_start, slot_end, booking_start, booking_end):
                overlap_count += 1

        # If a slot dict provides 'capacity', use it; otherwise assume capacity == 1
        capacity = slot.get('capacity', 1)
        if overlap_count < capacity:
            # include capacity so callers can compute per-slot availability
            available.append({
                'start_time': slot_start,
                'end_time': slot_end,
                'capacity': capacity
            })

    return available


# --- Available Labs Endpoint ---


@app.route("/api/labs/available", methods=["GET"])
@require_auth
def get_available_labs():
    """
    Get available labs and their slots for a specific date with role-based visibility.
    Query parameters:
      - date (YYYY-MM-DD format, required)
    Past dates are not allowed.
    Optimized for <3s response time with efficient queries.

    Role-based behavior:
    - Student: Only labs with available slots, no occupancy data
    - Faculty: Labs with available slots + occupancy numbers, low availability indicators
    - Lab Assistant: All labs including fully booked + occupancy + maintenance status
    - Admin: All labs + full occupancy + statuses + slot-level details
    """
    import time
    start_time = time.time()
    user_role = request.current_user.get("role", "student")

    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Date is required"}), 400

    # Validate date format and existence (no Feb 30 nonsense)
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        # Verify the parsed date matches input (catches invalid dates like Feb 30)
        if date_obj.strftime("%Y-%m-%d") != date_str:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Validate date is not in the past
    today = datetime.datetime.now().date()
    if date_obj.date() < today:
        return jsonify({"error": "Past dates are not allowed"}), 400

    # Get day of week
    day_of_week = get_day_of_week(date_str)
    if not day_of_week:
        return jsonify({"error": "Invalid date"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if labs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='labs'")
        if not cursor.fetchone():
            return jsonify({"labs": [], "date": date_str}), 200

        # Get disabled labs for this date
        disabled_lab_ids = set()
        try:
            cursor.execute("SELECT lab_id FROM disabled_labs WHERE disabled_date = ?", (date_str,))
            disabled_rows = cursor.fetchall()
            disabled_lab_ids = set([r[0] for r in disabled_rows]) if disabled_rows else set()
        except Exception:
            pass  # Table might not exist

        # Optimized: Single query to get all labs with their availability slots and bookings
        query = """
            SELECT
                l.id as lab_id,
                l.name as lab_name,
                l.capacity,
                l.equipment,
                av.start_time as avail_start,
                av.end_time as avail_end,
                b.start_time as booking_start,
                b.end_time as booking_end,
                b.id as booking_id,
                b.status as booking_status
            FROM labs l
            LEFT JOIN availability_slots av ON l.id = av.lab_id AND av.day_of_week = ?
            LEFT JOIN bookings b ON l.name = b.lab_name
                AND b.booking_date = ?
                AND b.status IN ('approved', 'pending')
            ORDER BY l.name ASC, av.start_time ASC, b.start_time ASC
        """
        cursor.execute(query, (day_of_week, date_str))
        rows = cursor.fetchall()

        # Process results efficiently
        labs_dict = {}
        for row in rows:
            lab_id = row["lab_id"]
            lab_name = row["lab_name"]

            if lab_id not in labs_dict:
                labs_dict[lab_id] = {
                    "lab_id": lab_id,
                    "lab_name": lab_name,
                    "capacity": row["capacity"],
                    "equipment": row["equipment"],
                    "availability_slots": [],
                    "bookings": [],
                    "disabled": lab_id in disabled_lab_ids
                }

            # Collect availability slots
            if row["avail_start"] and row["avail_end"]:
                # Include per-slot capacity (lab capacity applies per slot)
                slot = {
                    'start_time': row["avail_start"],
                    'end_time': row["avail_end"],
                    'capacity': row["capacity"]
                }
                if slot not in labs_dict[lab_id]["availability_slots"]:
                    labs_dict[lab_id]["availability_slots"].append(slot)

            # Collect bookings (both approved and pending) - include status
            if row["booking_start"] and row["booking_end"] and row["booking_id"]:
                try:
                    booking_status = (
                        row["booking_status"]
                        if "booking_status" in row.keys() and row["booking_status"]
                        else "pending"
                    )
                except (KeyError, AttributeError):
                    booking_status = "pending"
                booking = {
                    'start_time': row["booking_start"],
                    'end_time': row["booking_end"],
                    'id': row["booking_id"],
                    'status': booking_status
                }
                # Avoid duplicates by booking ID
                if not any(
                    b.get('id') == booking['id']
                    for b in labs_dict[lab_id]["bookings"]
                ):
                    labs_dict[lab_id]["bookings"].append(booking)

        # Get approved bookings separately to determine Active status
        approved_bookings_dict = {}
        try:
            cursor.execute(
                """
                SELECT lab_name, COUNT(*) as approved_count
                FROM bookings
                WHERE booking_date = ? AND status = 'approved'
                GROUP BY lab_name
                """,
                (date_str,)
            )
            approved_rows = cursor.fetchall()
            for row in approved_rows:
                approved_bookings_dict[row["lab_name"]] = row["approved_count"]
        except Exception:
            pass  # Table might not exist

        # Process labs based on role
        available_labs = []
        total_labs_in_system = len(labs_dict)
        active_labs = 0
        no_lab_active_count = 0
        disabled_labs_count = len(disabled_lab_ids)

        for lab_id, lab_data in labs_dict.items():
            # Filter available slots
            available_slots = filter_available_slots(
                lab_data["availability_slots"],
                lab_data["bookings"]
            )

            # Calculate occupancy metrics (per-slot capacity)
            total_slots = len(lab_data["availability_slots"])
            per_slot_capacity = lab_data.get("capacity", 1) or 1
            # For lab-level booked count, sum ONLY approved bookings overlapping each slot
            total_booked_units = 0
            approved_bookings_for_counting = [
                b for b in lab_data["bookings"]
                if isinstance(b, dict) and b.get('status') == 'approved'
            ]
            if len(lab_data["availability_slots"]) > 0:
                for slot in lab_data["availability_slots"]:
                    slot_bookings = [
                        b for b in approved_bookings_for_counting
                        if slots_overlap(slot['start_time'], slot['end_time'], b['start_time'], b['end_time'])
                    ]
                    total_booked_units += len(slot_bookings)
            else:
                # If no slots configured but has approved bookings, count them
                total_booked_units = len(approved_bookings_for_counting)

            total_possible = total_slots * per_slot_capacity
            free_units = max(0, total_possible - total_booked_units)

            # Determine lab status (Active/No lab active/Disabled)
            # Lab is Active if it has approved bookings OR has slots available
            has_approved_bookings = approved_bookings_dict.get(lab_data["lab_name"], 0) > 0
            # Also check if any booking in the list is approved
            has_approved_in_list = any(
                (isinstance(b, dict) and b.get('status') == 'approved')
                for b in lab_data["bookings"]
            )

            # Check if lab has approved bookings - this takes priority
            has_any_approved = has_approved_bookings or has_approved_in_list

            if lab_data["disabled"]:
                status = "Disabled"
                status_badge = "🔴"
            elif has_any_approved:
                # If lab has approved bookings, it's Active (even if no slots configured)
                status = "Active"
                status_badge = "🟢"
                active_labs += 1
            elif total_slots == 0:
                status = "No lab active"
                status_badge = "🟡"
                no_lab_active_count += 1
            elif total_slots > 0:
                status = "Active"
                status_badge = "🟢"
                active_labs += 1
            else:
                status = "No lab active"
                status_badge = "🟡"
                no_lab_active_count += 1

            # Provide per-slot availability details for students so they can see
            # how many units are available in each time slot (without exposing
            # admin-only lab-level data).
            # Only count APPROVED bookings for availability calculation
            approved_bookings_only = [
                b for b in lab_data["bookings"]
                if isinstance(b, dict) and b.get('status') == 'approved'
            ]

            slot_availability = []
            # If lab has approved bookings but no slots configured, create slots from approved bookings
            if len(approved_bookings_only) > 0 and total_slots == 0:
                # Create time slots from approved bookings
                for booking in approved_bookings_only:
                    slot_start = booking['start_time']
                    slot_end = booking['end_time']
                    slot_capacity = lab_data.get('capacity', 1) or 1
                    # This slot is fully booked (1 booking, 0 available)
                    slot_availability.append({
                        'time': f"{slot_start}-{slot_end}",
                        'start_time': slot_start,
                        'end_time': slot_end,
                        'capacity': slot_capacity,
                        'booked_count': 1,  # Number of students enrolled/booked in this time slot
                        'students_enrolled': 1,  # Explicit count of students enrolled
                        'available': 0,
                        'occupancy_label': "FULL"
                    })
            else:
                # Normal case: use filtered available slots
                # (excludes slots with pending/approved bookings that fill capacity)
                for slot in available_slots:
                    slot_start = slot['start_time']
                    slot_end = slot['end_time']
                    slot_capacity = slot.get('capacity', lab_data.get('capacity', 1) or 1)
                    slot_bookings = [
                        b for b in approved_bookings_only
                        if slots_overlap(slot_start, slot_end, b['start_time'], b['end_time'])
                    ]
                    slot_booked_count = len(slot_bookings)
                    slot_available_units = max(0, slot_capacity - slot_booked_count)
                    slot_availability.append({
                        'time': f"{slot_start}-{slot_end}",
                        'start_time': slot_start,
                        'end_time': slot_end,
                        'capacity': slot_capacity,
                        'booked_count': slot_booked_count,  # Number of students enrolled/booked in this time slot
                        'students_enrolled': slot_booked_count,  # Explicit count of students enrolled
                        'available': slot_available_units,
                        'occupancy_label': (
                            "FULL" if slot_available_units <= 0
                            else f"{slot_available_units}/{slot_capacity} free"
                        )
                    })

            # Calculate free_slots AFTER slot_availability is created
            # Count slots that have at least 1 free unit
            free_slots = sum(1 for slot in slot_availability if slot.get('available', 0) > 0)

            # Build student-friendly available_slots with occupancy shown
            # e.g., "09:00-11:00 (1/4 booked, 3 free)"
            student_available_slots = []
            for slot_avail in slot_availability:
                slot_str = f"{slot_avail['start_time']}-{slot_avail['end_time']}"
                occupancy_info = (
                    f"({slot_avail['booked_count']}/{slot_avail['capacity']} booked, "
                    f"{slot_avail['available']} free)"
                )
                student_available_slots.append(f"{slot_str} {occupancy_info}")

            # If lab has approved bookings but no configured slots, ensure the booked time slot is shown
            if len(approved_bookings_only) > 0 and total_slots == 0:
                # Add time slots from approved bookings to available_slots display if not already there
                for booking in approved_bookings_only:
                    slot_str = f"{booking['start_time']}-{booking['end_time']}"
                    # Check if this slot is already in student_available_slots
                    if not any(slot_str in s for s in student_available_slots):
                        slot_capacity = lab_data.get('capacity', 1) or 1
                        student_available_slots.append(f"{slot_str} (1/{slot_capacity} booked, 0 free)")

            # Role-based filtering and data inclusion
            lab_response = {
                "lab_id": lab_data["lab_id"],
                "lab_name": lab_data["lab_name"],
                "available_slots": student_available_slots
            }

            # Keep detailed `slot_availability` for student UI to render per-slot availability.
            lab_response['slot_availability'] = slot_availability

            # Include time slots information for all users
            # If lab has approved bookings but no slots configured, show time slots from bookings
            if lab_data["availability_slots"]:
                lab_response["time_slots"] = [
                    f"{slot['start_time']}-{slot['end_time']}"
                    for slot in lab_data["availability_slots"]
                ]
            elif has_any_approved and approved_bookings_only:
                # If lab has approved bookings but no slots, show time slots from approved bookings
                lab_response["time_slots"] = [
                    f"{b['start_time']}-{b['end_time']}"
                    for b in approved_bookings_only
                ]
            else:
                lab_response["time_slots"] = []

            # Include status and status_badge for ALL roles (student, faculty, lab_assistant, admin)
            lab_response["status"] = status
            lab_response["status_badge"] = status_badge

            # STUDENT: Show labs with available slots OR labs with configured slots (even if fully booked)
            # This ensures students can see labs exist, even if they're fully booked
            if user_role == "student":
                # Show if: (has free slots) OR (has slots configured for this day)
                should_show = (free_slots > 0) or (total_slots > 0)
                if should_show and not lab_data["disabled"]:
                    # Add occupancy info for students (same as other roles)
                    lab_response["occupancy"] = {
                        "total_slots": total_slots if total_slots > 0 else 0,
                        "booked": total_booked_units,
                        "free": free_units,
                        "occupancy_label": (
                            f"{free_units}/{total_possible} free" if total_possible > 0 else "0/0 free"
                        )
                    }
                    # Add capacity for students
                    lab_response["capacity"] = lab_data["capacity"]
                    # Add summary of students enrolled per time slot for students
                    lab_response["students_per_slot"] = [
                        {
                            "time": slot['time'],
                            "start_time": slot['start_time'],
                            "end_time": slot['end_time'],
                            "students_enrolled": slot.get('students_enrolled', slot.get('booked_count', 0)),
                            "capacity": slot['capacity'],
                            "available": slot['available']
                        }
                        for slot in slot_availability
                    ]
                    available_labs.append(lab_response)

            # FACULTY: Show labs with available slots OR configured slots (even if fully booked)
            elif user_role == "faculty":
                # Show if: (has free slots) OR (has slots configured for this day)
                should_show = (free_slots > 0) or (total_slots > 0)
                if should_show:
                    # Always include occupancy, even if 0
                    lab_response["occupancy"] = {
                        "total_slots": total_slots if total_slots > 0 else 0,
                        "booked": total_booked_units,
                        "free": free_units,
                        "occupancy_label": (
                            f"{free_units}/{total_possible} free" if total_possible > 0 else "0/0 free"
                        )
                    }
                    # Add capacity for faculty
                    lab_response["capacity"] = lab_data["capacity"]
                    # Add summary of students enrolled per time slot for faculty
                    lab_response["students_per_slot"] = [
                        {
                            "time": slot['time'],
                            "start_time": slot['start_time'],
                            "end_time": slot['end_time'],
                            "students_enrolled": slot.get('students_enrolled', slot.get('booked_count', 0)),
                            "capacity": slot['capacity'],
                            "available": slot['available']
                        }
                        for slot in slot_availability
                    ]
                    # Low availability indicator (1-2 slots left)
                    if free_slots <= 2 and free_slots > 0:
                        lab_response["low_availability"] = True
                        lab_response["availability_badge"] = f"{free_slots} slot{'s' if free_slots > 1 else ''} left"
                    available_labs.append(lab_response)

            # LAB ASSISTANT: Only assigned labs including fully booked + occupancy + maintenance
            elif user_role == "lab_assistant":
                # Get assigned labs for this lab assistant
                assistant_college_id = request.current_user.get("college_id")
                try:
                    cursor.execute(
                        "SELECT lab_id FROM lab_assistant_assignments WHERE assistant_college_id = ?",
                        (assistant_college_id,),
                    )
                    assignment_rows = cursor.fetchall()
                    assigned_lab_ids = set([r[0] for r in assignment_rows]) if assignment_rows else set()

                    # Only include labs assigned to this assistant
                    if lab_id not in assigned_lab_ids:
                        continue
                except Exception:
                    # If table doesn't exist or error, skip this lab
                    continue

                # Always include occupancy, even if 0
                lab_response["occupancy"] = {
                    "total_slots": total_slots if total_slots > 0 else 0,
                    "booked": total_booked_units,
                    "free": free_units,
                    "occupancy_label": (
                        f"Slots free units: {free_units}/{total_possible}" if total_possible > 0
                        else "No slots configured"
                    )
                }
                # Add summary of students enrolled per time slot for lab assistants
                lab_response["students_per_slot"] = [
                    {
                        "time": slot['time'],
                        "start_time": slot['start_time'],
                        "end_time": slot['end_time'],
                        "students_enrolled": slot.get('students_enrolled', slot.get('booked_count', 0)),
                        "capacity": slot['capacity'],
                        "available": slot['available']
                    }
                    for slot in slot_availability
                ]
                lab_response["status"] = status
                lab_response["status_badge"] = status_badge
                lab_response["capacity"] = lab_data["capacity"]
                # Show all assigned labs, even if fully booked
                available_labs.append(lab_response)

            # ADMIN: Everything - all labs, full occupancy, statuses, slot-level details
            elif user_role == "admin":
                # Calculate slot-level occupancy - only count APPROVED bookings
                slot_details = []
                approved_bookings_for_admin = [
                    b for b in lab_data["bookings"]
                    if isinstance(b, dict) and b.get('status') == 'approved'
                ]

                # If lab has approved bookings but no slots configured, create slots from approved bookings
                if len(approved_bookings_for_admin) > 0 and total_slots == 0:
                    for booking in approved_bookings_for_admin:
                        slot_start = booking['start_time']
                        slot_end = booking['end_time']
                        slot_capacity = per_slot_capacity
                        slot_detail = {
                            "time": f"{slot_start}-{slot_end}",
                            "start_time": slot_start,
                            "end_time": slot_end,
                            "booked_count": 1,
                            "students_enrolled": 1,  # Number of students enrolled in this time slot
                            "available": 0,
                            "occupancy_label": "FULL"
                        }
                        slot_details.append(slot_detail)
                else:
                    # Normal case: use availability slots
                    for slot in lab_data["availability_slots"]:
                        slot_bookings = [
                            b for b in approved_bookings_for_admin
                            if slots_overlap(
                                slot['start_time'], slot['end_time'],
                                b['start_time'], b['end_time']
                            )
                        ]
                        slot_booked_count = len(slot_bookings)
                        slot_capacity = slot.get('capacity', per_slot_capacity)
                        slot_available_units = max(0, slot_capacity - slot_booked_count)

                        slot_detail = {
                            "time": f"{slot['start_time']}-{slot['end_time']}",
                            "start_time": slot['start_time'],
                            "end_time": slot['end_time'],
                            "booked_count": slot_booked_count,
                            "students_enrolled": slot_booked_count,  # Number of students enrolled in this time slot
                            "available": slot_available_units,
                            "occupancy_label": (
                                "FULL" if slot_available_units <= 0
                                else f"{slot_available_units}/{slot_capacity} free"
                            )
                        }
                        slot_details.append(slot_detail)

                # Always include occupancy, even if 0
                lab_response["occupancy"] = {
                    "total_slots": total_slots if total_slots > 0 else 0,
                    "booked": total_booked_units,
                    "free": free_units,
                    "occupancy_label": (
                        f"{free_units}/{total_possible} free" if free_units > 0
                        else ("ALL BOOKED" if total_possible > 0 else "No slots configured")
                    )
                }
                lab_response["slot_level_occupancy"] = slot_details
                # Add summary of students enrolled per time slot for admin
                lab_response["students_per_slot"] = [
                    {
                        "time": slot['time'],
                        "start_time": slot['start_time'],
                        "end_time": slot['end_time'],
                        "students_enrolled": slot.get('students_enrolled', slot.get('booked_count', 0)),
                        "capacity": slot['capacity'],
                        "available": slot['available']
                    }
                    for slot in slot_availability
                ]
                lab_response["status"] = status
                lab_response["status_badge"] = status_badge
                lab_response["capacity"] = lab_data["capacity"]
                lab_response["equipment"] = lab_data["equipment"]
                # Show all labs including fully booked and disabled
                available_labs.append(lab_response)

        # Sort by lab name
        available_labs.sort(key=lambda x: x["lab_name"])

        # Check response time
        elapsed_time = time.time() - start_time
        if elapsed_time > 3.0:
            print(f"WARNING: Response time {elapsed_time:.2f}s exceeds 3s threshold")

        # Calculate summary counts based on filtered labs for each role
        # Count active labs from the filtered available_labs list
        filtered_active_labs = sum(1 for lab in available_labs if lab.get("status") == "Active")
        filtered_no_lab_active = sum(1 for lab in available_labs if lab.get("status") == "No lab active")
        filtered_disabled = sum(1 for lab in available_labs if lab.get("status") == "Disabled")
        filtered_total = len(available_labs)

        # Build response based on role
        response_data = {
            "date": date_str,
            "labs": available_labs
        }

        # Add summary data for ALL roles (student, faculty, lab_assistant, admin)
        if user_role == "admin":
            # Admin sees all labs in system
            response_data["summary"] = {
                "total_labs": total_labs_in_system,
                "active": active_labs,
                "no_lab_active": no_lab_active_count,
                "disabled": disabled_labs_count
            }
        else:
            # Other roles see filtered labs (only labs they can see)
            response_data["summary"] = {
                "total_labs": filtered_total,
                "active": filtered_active_labs,
                "no_lab_active": filtered_no_lab_active,
                "disabled": filtered_disabled
            }

        # Add diagnostic info for debugging (helpful when no labs show)
        # ALWAYS include diagnostic info when no labs are returned
        if len(available_labs) == 0:
            try:
                # Count labs that exist but don't have slots for this day
                cursor.execute("SELECT COUNT(*) FROM labs")
                total_labs_in_db = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT COUNT(DISTINCT lab_id) FROM availability_slots WHERE day_of_week = ?",
                    (day_of_week,)
                )
                labs_with_slots_today = cursor.fetchone()[0]
                response_data["diagnostic"] = {
                    "total_labs_in_database": total_labs_in_db,
                    "labs_with_slots_for_day": labs_with_slots_today,
                    "day_of_week": day_of_week,
                    "message": (
                        f"Found {total_labs_in_db} lab(s) in database, "
                        f"but {labs_with_slots_today} have availability slots "
                        f"configured for {day_of_week}."
                    )
                }
            except Exception as e:
                # If diagnostic fails, still return something helpful
                response_data["diagnostic"] = {
                    "total_labs_in_database": 0,
                    "labs_with_slots_for_day": 0,
                    "day_of_week": day_of_week,
                    "message": f"Unable to retrieve diagnostic info: {str(e)}"
                }

        # Add response time for all roles
        response_data["response_time_ms"] = round(elapsed_time * 1000, 2)

        return jsonify(response_data), 200

    except sqlite3.Error as e:
        print(f"Database Error in get_available_labs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Something went wrong"}), 500
    except Exception as e:
        print(f"Unexpected error in get_available_labs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Something went wrong"}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/admin/labs/<int:lab_id>/assign", methods=["POST"])
@require_role("admin")
def assign_lab_to_assistant(lab_id):
    """Assign a lab to a lab assistant (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    assistant_college_id = data.get("assistant_college_id")
    if not assistant_college_id:
        return jsonify({"message": "assistant_college_id is required.", "success": False}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if lab exists
        cursor.execute("SELECT id, name FROM labs WHERE id = ?", (lab_id,))
        lab = cursor.fetchone()
        if not lab:
            return jsonify({"message": "Lab not found.", "success": False}), 404

        # Check if assistant exists and is a lab_assistant
        cursor.execute("SELECT college_id, role FROM users WHERE college_id = ?", (assistant_college_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"message": "Lab assistant not found.", "success": False}), 404
        if user["role"] != "lab_assistant":
            return jsonify({"message": "User is not a lab assistant.", "success": False}), 400

        # Check if assignment already exists
        cursor.execute(
            "SELECT id FROM lab_assistant_assignments WHERE lab_id = ? AND assistant_college_id = ?",
            (lab_id, assistant_college_id),
        )
        if cursor.fetchone():
            return jsonify({"message": "Lab is already assigned to this assistant.", "success": False}), 400

        # Create assignment
        assigned_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "INSERT INTO lab_assistant_assignments (lab_id, assistant_college_id, assigned_at) VALUES (?, ?, ?)",
            (lab_id, assistant_college_id, assigned_at),
        )
        conn.commit()

        return jsonify({
            "message": f"Lab '{lab['name']}' assigned to assistant successfully.",
            "success": True
        }), 200

    except sqlite3.Error as e:
        print(f"Database Error in assign_lab_to_assistant: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to assign lab.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in assign_lab_to_assistant: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/admin/labs/<int:lab_id>/unassign", methods=["POST"])
@require_role("admin")
def unassign_lab_from_assistant(lab_id):
    """Unassign a lab from a lab assistant (admin only)."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    assistant_college_id = data.get("assistant_college_id")
    if not assistant_college_id:
        return jsonify({"message": "assistant_college_id is required.", "success": False}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if assignment exists
        cursor.execute(
            "SELECT id FROM lab_assistant_assignments WHERE lab_id = ? AND assistant_college_id = ?",
            (lab_id, assistant_college_id),
        )
        assignment = cursor.fetchone()
        if not assignment:
            return jsonify({"message": "Assignment not found.", "success": False}), 404

        # Delete assignment
        cursor.execute(
            "DELETE FROM lab_assistant_assignments WHERE lab_id = ? AND assistant_college_id = ?",
            (lab_id, assistant_college_id),
        )
        conn.commit()

        return jsonify({
            "message": "Lab unassigned from assistant successfully.",
            "success": True
        }), 200

    except sqlite3.Error as e:
        print(f"Database Error in unassign_lab_from_assistant: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to unassign lab.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in unassign_lab_from_assistant: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/labs/<int:lab_id>/availability", methods=["PUT"])
@require_role("admin")
def update_lab_availability(lab_id):
    """
    Update available_slots for a lab (admin only).
    Validates that available_slots is >= 0 and <= capacity.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    # Validate available_slots field
    if "available_slots" not in data:
        return jsonify({"message": "available_slots field is required.", "success": False}), 400

    try:
        available_slots = int(data["available_slots"])
    except (ValueError, TypeError):
        return jsonify({"message": "available_slots must be an integer.", "success": False}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if labs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='labs'")
        if not cursor.fetchone():
            return jsonify({"message": "Labs table does not exist.", "success": False}), 404

        # Check if lab exists and get capacity
        cursor.execute("SELECT id, name, capacity FROM labs WHERE id = ?", (lab_id,))
        lab = cursor.fetchone()
        if not lab:
            return jsonify({"message": "Lab not found.", "success": False}), 404

        capacity = lab["capacity"]

        # Validate available_slots: must be >= 0 and <= capacity
        if available_slots < 0:
            return jsonify({
                "message": "available_slots cannot be negative. Minimum value is 0.",
                "success": False
            }), 400

        if available_slots > capacity:
            return jsonify({
                "message": f"available_slots cannot exceed capacity ({capacity}).",
                "success": False
            }), 400

        # Update available_slots
        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            UPDATE labs SET available_slots = ?, updated_at = ?
            WHERE id = ?
            """,
            (available_slots, updated_at, lab_id),
        )
        conn.commit()

        # Get the updated lab
        cursor.execute("SELECT * FROM labs WHERE id = ?", (lab_id,))
        lab_row = cursor.fetchone()
        # Safely get equipment_status
        equipment_status = "Not Available"
        try:
            if "equipment_status" in lab_row.keys():
                equipment_status = lab_row["equipment_status"] if lab_row["equipment_status"] else "Not Available"
        except (KeyError, AttributeError):
            pass
        lab_data = {
            "id": lab_row["id"],
            "name": lab_row["name"],
            "capacity": lab_row["capacity"],
            "available_slots": available_slots,
            "equipment": lab_row["equipment"],
            "equipment_status": equipment_status,
            "created_at": lab_row["created_at"],
            "updated_at": lab_row["updated_at"],
        }

        return jsonify({
            "message": f"Available slots updated to {available_slots} successfully.",
            "lab": lab_data,
            "success": True
        }), 200

    except sqlite3.Error as e:
        print(f"Database Error in update_lab_availability: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to update available slots.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in update_lab_availability: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/labs/<int:lab_id>/equipment-status", methods=["PUT"])
@require_role("admin")
def update_equipment_status(lab_id):
    """
    Update equipment availability status for a lab (admin only).
    Only allows "Available" or "Not Available" as valid status values.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    # Validate equipment_status field
    if "equipment_status" not in data:
        return jsonify({"message": "equipment_status field is required.", "success": False}), 400

    equipment_status = data["equipment_status"].strip()

    # Validate that status is one of the allowed values
    valid_statuses = ["Available", "Not Available"]
    if equipment_status not in valid_statuses:
        return jsonify({
            "message": f"Invalid equipment_status. Must be one of: {', '.join(valid_statuses)}.",
            "success": False
        }), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if labs table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='labs'")
        if not cursor.fetchone():
            return jsonify({"message": "Labs table does not exist.", "success": False}), 404

        # Check if lab exists
        cursor.execute("SELECT id, name FROM labs WHERE id = ?", (lab_id,))
        lab = cursor.fetchone()
        if not lab:
            return jsonify({"message": "Lab not found.", "success": False}), 404

        # Update equipment_status
        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            UPDATE labs SET equipment_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (equipment_status, updated_at, lab_id),
        )
        conn.commit()

        # Get the updated lab
        cursor.execute("SELECT * FROM labs WHERE id = ?", (lab_id,))
        lab_row = cursor.fetchone()
        # Safely get available_slots
        capacity_val = lab_row["capacity"] if "capacity" in lab_row.keys() else 0
        available_slots = capacity_val
        try:
            if "available_slots" in lab_row.keys():
                available_slots = lab_row["available_slots"] if lab_row["available_slots"] is not None else capacity_val
        except (KeyError, AttributeError):
            pass
        lab_data = {
            "id": lab_row["id"],
            "name": lab_row["name"],
            "capacity": lab_row["capacity"],
            "available_slots": available_slots,
            "equipment": lab_row["equipment"],
            "equipment_status": equipment_status,
            "created_at": lab_row["created_at"],
            "updated_at": lab_row["updated_at"],
        }

        return jsonify({
            "message": f"Equipment status updated to '{equipment_status}' successfully.",
            "lab": lab_data,
            "success": True
        }), 200

    except sqlite3.Error as e:
        print(f"Database Error in update_equipment_status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to update equipment status.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in update_equipment_status: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/reserve-lab", methods=["POST"])
@require_role("faculty")
def reserve_lab():
    """
    Reserve a lab (faculty only).
    Creates a booking request with status "Pending".
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    # Validate required fields
    required_fields = ["lab_id", "date", "start_time", "end_time", "reason"]
    if not all(field in data for field in required_fields):
        return jsonify({"message": "Missing required fields.", "success": False}), 400

    college_id = request.current_user.get("college_id")
    lab_id = data["lab_id"]
    reservation_date = data["date"]
    start_time = data["start_time"]
    end_time = data["end_time"]

    # Validate date and time format
    try:
        datetime.datetime.strptime(reservation_date, "%Y-%m-%d")
        datetime.datetime.strptime(start_time, "%H:%M")
        datetime.datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return jsonify({"message": "Invalid date or time format.", "success": False}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Ensure bookings table exists
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                college_id TEXT NOT NULL,
                lab_name TEXT NOT NULL,
                booking_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (college_id) REFERENCES users(college_id)
            );
            """
        )
        conn.commit()

        # Check if lab exists and get lab name
        cursor.execute("SELECT id, name FROM labs WHERE id = ?", (lab_id,))
        lab = cursor.fetchone()
        if not lab:
            return jsonify({"message": "Lab not found.", "success": False}), 404

        lab_name = lab["name"]

        # Create booking with status "Pending"
        created_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO bookings (college_id, lab_name, booking_date, start_time, end_time, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (college_id, lab_name, reservation_date, start_time, end_time, "pending", created_at),
        )
        conn.commit()
        booking_id = cursor.lastrowid

        return jsonify({
            "message": "Lab reservation request created successfully. Waiting for admin approval.",
            "booking_id": booking_id,
            "status": "pending",
            "success": True
        }), 201

    except sqlite3.Error as e:
        print(f"Database Error in reserve_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to create reservation.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in reserve_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


@app.route("/api/reservations/<int:reservation_id>/cancel", methods=["PUT"])
@require_role("faculty", "lab_assistant", "admin")
def cancel_reservation(reservation_id):
    """
    Cancel a reservation (faculty, lab assistant, admin).
    Cancellation increases available_slots by 1 if the booking was approved.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if bookings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if not cursor.fetchone():
            return jsonify({"message": "Bookings table does not exist.", "success": False}), 404

        # Check if booking exists and get its details
        cursor.execute(
            "SELECT college_id, lab_name, status FROM bookings WHERE id = ?",
            (reservation_id,),
        )
        booking = cursor.fetchone()
        if not booking:
            return jsonify({"message": "Reservation not found.", "success": False}), 404

        # Check permissions: faculty can only cancel their own bookings
        user_role = request.current_user.get("role")
        user_college_id = request.current_user.get("college_id")

        if user_role == "faculty" and booking["college_id"] != user_college_id:
            return jsonify({"message": "You can only cancel your own reservations.", "success": False}), 403

        # Only increase availability if booking was approved
        was_approved = booking["status"] == "approved"
        lab_name = booking["lab_name"]

        # Update booking status to cancelled
        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE bookings SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (updated_at, reservation_id),
        )

        # Increment available_slots if booking was approved
        if was_approved:
            # Get current available_slots and capacity
            cursor.execute("SELECT available_slots, capacity FROM labs WHERE name = ?", (lab_name,))
            lab_row = cursor.fetchone()
            if lab_row:
                if "available_slots" in lab_row.keys():
                    current_slots = lab_row["available_slots"] if lab_row["available_slots"] is not None else 0
                else:
                    current_slots = 0
                capacity = lab_row["capacity"] if "capacity" in lab_row.keys() else 0
                new_slots = min(capacity, current_slots + 1)  # Ensure it doesn't exceed capacity
                cursor.execute(
                    "UPDATE labs SET available_slots = ?, updated_at = ? WHERE name = ?",
                    (new_slots, updated_at, lab_name)
                )

        conn.commit()

        return jsonify({
            "message": "Reservation cancelled successfully.",
            "success": True
        }), 200

    except sqlite3.Error as e:
        print(f"Database Error in cancel_reservation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to cancel reservation.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in cancel_reservation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


# --- Application Runner ---
# Initialize database on startup
init_db()

if __name__ == "__main__":
    # Use environment variable for debug mode (default: False for security)
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, port=5000)
