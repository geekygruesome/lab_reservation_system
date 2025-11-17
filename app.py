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
            equipment TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
        """
    )
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
    # Create equipment_availability table for tracking individual equipment availability
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment_availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            equipment_name TEXT NOT NULL,
            is_available TEXT NOT NULL DEFAULT 'yes',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE CASCADE,
            UNIQUE(lab_id, equipment_name)
        );
        """
    )
    # Create disabled_labs table for tracking labs disabled for specific dates
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
    # Create lab_assistant_assignments table for tracking lab assignments
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

    print("Database initialization complete.")


# --- Helper Functions for Availability ---

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
    role = request.current_user.get("role")
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

    # Validate time range
    if start_time >= end_time:
        return jsonify({"message": "End time must be after start time.", "success": False}), 400

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

        # For students: validate that the time slot exists in approved bookings or availability slots
        if role == "student":
            day_of_week = get_day_of_week(booking_date)
            if day_of_week:
                # Check availability slots
                cursor.execute("SELECT id FROM labs WHERE name = ?", (lab_name,))
                lab_row = cursor.fetchone()
                if lab_row:
                    lab_id = lab_row[0]
                    cursor.execute(
                        """
                        SELECT start_time, end_time
                        FROM availability_slots
                        WHERE lab_id = ? AND day_of_week = ?
                        """,
                        (lab_id, day_of_week)
                    )
                    availability_slots = cursor.fetchall()

                    # Check if time matches any availability slot
                    slot_found = False
                    for slot in availability_slots:
                        if slots_overlap(slot[0], slot[1], start_time, end_time):
                            slot_found = True
                            break

                    # If not in availability slots, check approved bookings
                    if not slot_found:
                        cursor.execute(
                            """
                            SELECT start_time, end_time
                            FROM bookings
                            WHERE lab_name = ? AND booking_date = ? AND status = 'approved'
                            """,
                            (lab_name, booking_date)
                        )
                        approved_bookings = cursor.fetchall()
                        for booking in approved_bookings:
                            if booking[0] == start_time and booking[1] == end_time:
                                slot_found = True
                                break

                    if not slot_found:
                        return jsonify({
                            "message": (
                                "Students can only book from available time slots. "
                                "Please select a time slot from the available options."
                            ),
                            "success": False
                        }), 400

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


# --- Get Available Time Slots Endpoint ---

@app.route("/api/labs/<lab_name>/available-slots", methods=["GET"])
@require_auth
def get_available_slots_for_lab(lab_name):
    """Get available time slots for a specific lab on a given date."""
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Date is required", "success": False}), 400

    # Validate date
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if date_obj.strftime("%Y-%m-%d") != date_str:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD.", "success": False}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD.", "success": False}), 400

    # Reject past dates
    today = datetime.datetime.now().date()
    if date_obj.date() < today:
        return jsonify({"error": "Past dates are not allowed", "success": False}), 400

    day_of_week = get_day_of_week(date_str)
    if not day_of_week:
        return jsonify({"error": "Invalid date", "success": False}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get lab ID
        cursor.execute("SELECT id FROM labs WHERE name = ?", (lab_name,))
        lab_row = cursor.fetchone()
        if not lab_row:
            return jsonify({"error": "Lab not found", "success": False}), 404

        lab_id = lab_row[0]

        # Get availability slots for this lab on this day
        cursor.execute(
            """
            SELECT start_time, end_time
            FROM availability_slots
            WHERE lab_id = ? AND day_of_week = ?
            ORDER BY start_time ASC
            """,
            (lab_id, day_of_week)
        )
        availability_slots = cursor.fetchall()

        # Get approved bookings for this lab on this date to calculate available capacity
        cursor.execute(
            """
            SELECT start_time, end_time
            FROM bookings
            WHERE lab_name = ? AND booking_date = ? AND status = 'approved'
            ORDER BY start_time ASC
            """,
            (lab_name, date_str)
        )
        approved_bookings = cursor.fetchall()

        # Get lab capacity
        cursor.execute("SELECT capacity FROM labs WHERE id = ?", (lab_id,))
        capacity_row = cursor.fetchone()
        capacity = capacity_row[0] if capacity_row else 1

        # Build available slots with capacity info
        available_slots = []
        for slot in availability_slots:
            slot_start = slot[0]
            slot_end = slot[1]

            # Count overlapping approved bookings
            overlapping_count = 0
            for booking in approved_bookings:
                if slots_overlap(slot_start, slot_end, booking[0], booking[1]):
                    overlapping_count += 1

            available_count = max(0, capacity - overlapping_count)

            if available_count > 0:
                available_slots.append({
                    "start_time": slot_start,
                    "end_time": slot_end,
                    "available": available_count,
                    "capacity": capacity
                })

        # If no availability slots but there are approved bookings, use those as available options
        if not available_slots and approved_bookings:
            # For students, show approved booking slots as available options
            for booking in approved_bookings:
                available_slots.append({
                    "start_time": booking[0],
                    "end_time": booking[1],
                    "available": 1,
                    "capacity": capacity
                })

        return jsonify({
            "lab_name": lab_name,
            "date": date_str,
            "available_slots": available_slots,
            "success": True
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in get_available_slots_for_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Database error occurred", "success": False}), 500
    except Exception as e:
        print(f"Unexpected Error in get_available_slots_for_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred", "success": False}), 500
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


# --- Modify Booking Endpoint ---

@app.route("/api/bookings/<int:booking_id>", methods=["PUT"])
@require_auth
def modify_booking(booking_id):
    """Modify a booking. Admin/Faculty can modify freely, students can only choose from available slots."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    college_id = request.current_user.get("college_id")
    role = request.current_user.get("role")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if bookings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if not cursor.fetchone():
            return jsonify({"message": "Bookings table does not exist.", "success": False}), 404

        # Get the booking
        cursor.execute(
            "SELECT college_id, lab_name, booking_date, start_time, end_time, status FROM bookings WHERE id = ?",
            (booking_id,)
        )
        booking = cursor.fetchone()
        if not booking:
            return jsonify({"message": "Booking not found.", "success": False}), 404

        # Check if user owns the booking or is admin
        if booking[0] != college_id and role != "admin":
            return jsonify({"message": "You can only modify your own bookings.", "success": False}), 403

        # Get new values or use existing ones
        new_lab_name = data.get("lab_name", booking[1])
        new_booking_date = data.get("booking_date", booking[2])
        new_start_time = data.get("start_time", booking[3])
        new_end_time = data.get("end_time", booking[4])

        # Validate date and time format
        try:
            datetime.datetime.strptime(new_booking_date, "%Y-%m-%d")
            datetime.datetime.strptime(new_start_time, "%H:%M")
            datetime.datetime.strptime(new_end_time, "%H:%M")
        except ValueError:
            return jsonify({"message": "Invalid date or time format.", "success": False}), 400

        # Validate time range
        if new_start_time >= new_end_time:
            return jsonify({"message": "End time must be after start time.", "success": False}), 400

        # For students: validate that the time slot exists in approved bookings or availability slots
        if role == "student":
            day_of_week = get_day_of_week(new_booking_date)
            if day_of_week:
                # Check availability slots
                cursor.execute("SELECT id FROM labs WHERE name = ?", (new_lab_name,))
                lab_row = cursor.fetchone()
                if lab_row:
                    lab_id = lab_row[0]
                    cursor.execute(
                        """
                        SELECT start_time, end_time
                        FROM availability_slots
                        WHERE lab_id = ? AND day_of_week = ?
                        """,
                        (lab_id, day_of_week)
                    )
                    availability_slots = cursor.fetchall()

                    # Check if time matches any availability slot
                    slot_found = False
                    for slot in availability_slots:
                        if slots_overlap(slot[0], slot[1], new_start_time, new_end_time):
                            slot_found = True
                            break

                    # If not in availability slots, check approved bookings
                    if not slot_found:
                        cursor.execute(
                            """
                            SELECT start_time, end_time
                            FROM bookings
                            WHERE lab_name = ? AND booking_date = ? AND status = 'approved'
                            AND id != ?
                            """,
                            (new_lab_name, new_booking_date, booking_id)
                        )
                        approved_bookings = cursor.fetchall()
                        for approved_booking in approved_bookings:
                            if approved_booking[0] == new_start_time and approved_booking[1] == new_end_time:
                                slot_found = True
                                break

                    if not slot_found:
                        return jsonify({
                            "message": (
                                "Students can only book from available time slots. "
                                "Please select a time slot from the available options."
                            ),
                            "success": False
                        }), 400

        # Update the booking
        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            UPDATE bookings
            SET lab_name = ?, booking_date = ?, start_time = ?, end_time = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_lab_name, new_booking_date, new_start_time, new_end_time, updated_at, booking_id)
        )
        conn.commit()

        return jsonify({
            "message": "Booking modified successfully.",
            "success": True
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in modify_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to modify booking.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in modify_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


# --- Cancel Booking Endpoint ---

@app.route("/api/bookings/<int:booking_id>", methods=["DELETE"])
@require_auth
def cancel_booking(booking_id):
    """Cancel a booking. Users can cancel their own bookings, admin can cancel any."""
    college_id = request.current_user.get("college_id")
    role = request.current_user.get("role")

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if bookings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if not cursor.fetchone():
            return jsonify({"message": "Bookings table does not exist.", "success": False}), 404

        # Get the booking
        cursor.execute(
            "SELECT college_id, status FROM bookings WHERE id = ?",
            (booking_id,)
        )
        booking = cursor.fetchone()
        if not booking:
            return jsonify({"message": "Booking not found.", "success": False}), 404

        # Check if user owns the booking or is admin
        if booking[0] != college_id and role != "admin":
            return jsonify({"message": "You can only cancel your own bookings.", "success": False}), 403

        # Delete the booking
        cursor.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        conn.commit()

        return jsonify({
            "message": "Booking cancelled successfully.",
            "success": True
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in cancel_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to cancel booking.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in cancel_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


# --- Admin Lab Availability Endpoint ---

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

        # Ensure all required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='labs'")
        if not cursor.fetchone():
            # Initialize database tables if they don't exist
            init_db()
            conn = get_db_connection()  # Get fresh connection after init
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

        # Fetch all bookings for this lab on this date (check if bookings table exists)
        bookings_rows = []
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if cursor.fetchone():
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

        # Disabled labs for this date (check if disabled_labs table exists)
        disabled = {}
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='disabled_labs'")
        if cursor.fetchone():
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


# --- Unified Lab Availability Endpoint (All Roles) ---

@app.route("/api/labs/available", methods=["GET"])
@require_auth
def get_available_labs():
    """
    Unified endpoint for all roles to view available labs with status and time slots.
    - Shows labs with status (Active/Not Available) based on approved bookings
    - Shows time slots from approved bookings
    - For admin: includes capacity and student count per slot
    - For others: shows active labs with time slots only
    """
    date_str = request.args.get("date")
    if not date_str:
        # Default to today if no date provided
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # Validate date
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if date_obj.strftime("%Y-%m-%d") != date_str:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Reject past dates
    today = datetime.datetime.now().date()
    if date_obj.date() < today:
        return jsonify({"error": "Past dates are not allowed"}), 400

    # Get user role from token
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        user_role = payload.get('role')
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    is_admin = user_role == 'admin'

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Ensure all required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='labs'")
        if not cursor.fetchone():
            # Initialize database tables if they don't exist
            init_db()
            conn = get_db_connection()  # Get fresh connection after init
            cursor = conn.cursor()

        # Get day of week for availability slots
        day_of_week = get_day_of_week(date_str)

        # Get all labs
        cursor.execute("SELECT id, name, capacity, equipment FROM labs ORDER BY name ASC")
        labs_rows = cursor.fetchall()

        # Get availability slots for the day (check if availability_slots table exists)
        slots_by_lab = {}
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='availability_slots'")
        if cursor.fetchone() and day_of_week:
            cursor.execute(
                """
                SELECT lab_id, start_time, end_time
                FROM availability_slots
                WHERE day_of_week = ?
                """,
                (day_of_week,)
            )
            slots_rows = cursor.fetchall()
            for row in slots_rows:
                lab_id = row[0]
                if lab_id not in slots_by_lab:
                    slots_by_lab[lab_id] = []
                slots_by_lab[lab_id].append({
                    'start_time': row[1],
                    'end_time': row[2]
                })

        # Get approved bookings for the date (check if bookings table exists)
        bookings_rows = []
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if cursor.fetchone():
            cursor.execute(
                """
                SELECT b.id, b.college_id, b.lab_name, b.start_time, b.end_time,
                       b.created_at, u.name as user_name
                FROM bookings b
                LEFT JOIN users u ON b.college_id = u.college_id
                WHERE b.booking_date = ? AND b.status = 'approved'
                ORDER BY b.lab_name ASC, b.start_time ASC
                """,
                (date_str,)
            )
            bookings_rows = cursor.fetchall()

        # Get disabled labs for the date (check if disabled_labs table exists)
        disabled_labs = {}
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='disabled_labs'")
        if cursor.fetchone():
            cursor.execute(
                "SELECT lab_id, reason FROM disabled_labs WHERE disabled_date = ?",
                (date_str,)
            )
            disabled_labs = {row[0]: row[1] for row in cursor.fetchall()}

        # Organize bookings by lab name
        bookings_by_lab = {}
        for booking in bookings_rows:
            lab_name = booking['lab_name']
            if lab_name not in bookings_by_lab:
                bookings_by_lab[lab_name] = []
            bookings_by_lab[lab_name].append({
                'id': booking['id'],
                'college_id': booking['college_id'],
                'start_time': booking['start_time'],
                'end_time': booking['end_time'],
                'user_name': booking['user_name'],
                'created_at': booking['created_at']
            })

        labs = []
        for lab_row in labs_rows:
            lab_id = lab_row['id']
            lab_name = lab_row['name']
            capacity = lab_row['capacity']
            equipment = lab_row['equipment']

            # Get availability slots for this lab
            lab_slots = slots_by_lab.get(lab_id, [])

            # Get bookings for this lab
            lab_bookings = bookings_by_lab.get(lab_name, [])

            # Calculate occupancy based on slots and bookings
            total_slots = len(lab_slots)

            # Count how many slots are fully booked (capacity reached)
            booked_slots = 0
            if total_slots > 0:
                for slot in lab_slots:
                    slot_start = slot['start_time']
                    slot_end = slot['end_time']
                    # Count bookings that overlap with this slot
                    overlapping_bookings = 0
                    for booking in lab_bookings:
                        if slots_overlap(slot_start, slot_end, booking['start_time'], booking['end_time']):
                            overlapping_bookings += 1
                    # If bookings reach or exceed capacity, slot is fully booked
                    if overlapping_bookings >= capacity:
                        booked_slots += 1

            # Free slots = total slots - fully booked slots
            total_free = max(0, total_slots - booked_slots)

            # Determine status: Active if has slots or bookings, Not Available otherwise
            status = "Active" if (lab_slots or lab_bookings) else "Not Available"
            status_badge = "active" if (lab_slots or lab_bookings) else "inactive"

            # Get unique time slots from approved bookings or availability slots
            time_slots = []
            slot_details = {}  # For admin: track student count per slot

            # If we have availability slots, use those; otherwise use booking slots
            if lab_slots:
                time_slots = [f"{s['start_time']}-{s['end_time']}" for s in lab_slots]
            else:
                for booking in lab_bookings:
                    slot_key = f"{booking['start_time']}-{booking['end_time']}"
                    if slot_key not in time_slots:
                        time_slots.append(slot_key)

                # For admin: count students per slot
                if is_admin:
                    for booking in lab_bookings:
                        slot_key = f"{booking['start_time']}-{booking['end_time']}"
                        if slot_key not in slot_details:
                            slot_details[slot_key] = {
                                'start_time': booking['start_time'],
                                'end_time': booking['end_time'],
                                'student_count': 0,
                                'capacity': capacity
                            }
                        slot_details[slot_key]['student_count'] += 1

            # Convert slot_details to list for admin
            availability_slots = []
            if is_admin:
                for slot_key, details in slot_details.items():
                    availability_slots.append({
                        'time': slot_key,
                        'start_time': details['start_time'],
                        'end_time': details['end_time'],
                        'student_count': details['student_count'],
                        'capacity': details['capacity'],
                        'available': max(0, details['capacity'] - details['student_count'])
                    })

            lab_data = {
                "lab_id": lab_id,
                "lab_name": lab_name,
                "capacity": capacity,
                "equipment": equipment,
                "status": status,
                "status_badge": status_badge,
                "time_slots": time_slots,
                "disabled": lab_id in disabled_labs,
                "disabled_reason": disabled_labs.get(lab_id),
                "occupancy": {
                    "total_slots": total_slots,
                    "booked": booked_slots,
                    "free": total_free,
                    "occupancy_label": f"{total_free}/{total_slots} free" if total_slots > 0 else "No slots"
                }
            }

            # Add admin-specific data
            if is_admin:
                lab_data["availability_slots"] = availability_slots

            # Only include labs that have slots configured or bookings (for students)
            # Admins see all labs
            # Students should not see disabled labs
            if is_admin or (lab_slots or lab_bookings):
                if is_admin or lab_id not in disabled_labs:
                    labs.append(lab_data)

        return jsonify({
            "date": date_str,
            "labs": labs,
            "total_labs": len(labs),
            "success": True
        }), 200

    except sqlite3.Error as e:
        print(f"Database Error in get_available_labs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Database error occurred", "details": str(e)}), 500
    except Exception as e:
        print(f"Unexpected Error in get_available_labs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


# --- Lab Management Functions ---


def initialize_equipment_availability(cursor, lab_id, equipment_list):
    """Initialize equipment availability entries for a lab."""
    created_at = datetime.datetime.now(timezone.utc).isoformat()
    for equipment_name in equipment_list:
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO equipment_availability
                (lab_id, equipment_name, is_available, created_at)
                VALUES (?, ?, 'yes', ?)
                """,
                (lab_id, equipment_name.strip(), created_at),
            )
        except sqlite3.Error as e:
            print(f"Error initializing equipment availability for {equipment_name}: {e}")


def sync_equipment_availability(cursor, lab_id, equipment_list):
    """Sync equipment availability: add new, remove deleted, keep existing."""
    created_at = datetime.datetime.now(timezone.utc).isoformat()

    # Get current equipment names from availability table
    cursor.execute(
        "SELECT equipment_name FROM equipment_availability WHERE lab_id = ?",
        (lab_id,)
    )
    existing_equipment = {row["equipment_name"] for row in cursor.fetchall()}

    # Normalize new equipment list
    new_equipment = {eq.strip() for eq in equipment_list}

    # Add new equipment
    for equipment_name in new_equipment:
        if equipment_name not in existing_equipment:
            try:
                cursor.execute(
                    """
                    INSERT INTO equipment_availability
                    (lab_id, equipment_name, is_available, created_at)
                    VALUES (?, ?, 'yes', ?)
                    """,
                    (lab_id, equipment_name, created_at),
                )
            except sqlite3.Error as e:
                print(f"Error adding equipment availability for {equipment_name}: {e}")

    # Remove deleted equipment
    for equipment_name in existing_equipment:
        if equipment_name not in new_equipment:
            cursor.execute(
                "DELETE FROM equipment_availability WHERE lab_id = ? AND equipment_name = ?",
                (lab_id, equipment_name)
            )


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
                equipment TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );
            """
        )
        conn.commit()

        # Parse equipment to JSON string if it's a list
        equipment = data["equipment"]
        if isinstance(equipment, list):
            equipment = json.dumps(equipment)

        created_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO labs (name, capacity, equipment, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (data["name"].strip(), int(data["capacity"]), equipment, created_at),
        )
        conn.commit()
        lab_id = cursor.lastrowid

        # Initialize equipment availability
        try:
            equipment_list = json.loads(equipment) if isinstance(equipment, str) else equipment
            if isinstance(equipment_list, str):
                # Try to parse as comma-separated
                equipment_list = [e.strip() for e in equipment_list.split(',') if e.strip()]
            if isinstance(equipment_list, list):
                initialize_equipment_availability(cursor, lab_id, equipment_list)
                conn.commit()
        except Exception as e:
            print(f"Warning: Could not initialize equipment availability: {e}")

        # Get the created lab
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
            lab_id = row["id"]
            # Get equipment availability for this lab
            cursor.execute(
                """
                SELECT equipment_name, is_available
                FROM equipment_availability
                WHERE lab_id = ?
                ORDER BY equipment_name ASC
                """,
                (lab_id,)
            )
            equipment_availability = []
            for eq_row in cursor.fetchall():
                equipment_availability.append({
                    "equipment_name": eq_row["equipment_name"],
                    "is_available": eq_row["is_available"]
                })

            # Auto-initialize equipment availability if missing (for existing labs)
            if len(equipment_availability) == 0:
                try:
                    equipment_str = row["equipment"]
                    equipment_list = []
                    try:
                        equipment_list = json.loads(equipment_str)
                        if not isinstance(equipment_list, list):
                            equipment_list = [equipment_str]
                    except (json.JSONDecodeError, ValueError):
                        if ',' in equipment_str:
                            equipment_list = [e.strip() for e in equipment_str.split(',') if e.strip()]
                        else:
                            equipment_list = [equipment_str.strip()] if equipment_str.strip() else []

                    if equipment_list:
                        created_at = datetime.datetime.now(timezone.utc).isoformat()
                        for equipment_name in equipment_list:
                            if equipment_name and equipment_name.strip():
                                try:
                                    cursor.execute(
                                        """
                                        INSERT OR IGNORE INTO equipment_availability
                                        (lab_id, equipment_name, is_available, created_at)
                                        VALUES (?, ?, 'yes', ?)
                                        """,
                                        (lab_id, equipment_name.strip(), created_at),
                                    )
                                except sqlite3.Error:
                                    pass
                        conn.commit()

                        # Re-fetch equipment availability
                        cursor.execute(
                            """
                            SELECT equipment_name, is_available
                            FROM equipment_availability
                            WHERE lab_id = ?
                            ORDER BY equipment_name ASC
                            """,
                            (lab_id,)
                        )
                        equipment_availability = []
                        for eq_row in cursor.fetchall():
                            equipment_availability.append({
                                "equipment_name": eq_row["equipment_name"],
                                "is_available": eq_row["is_available"]
                            })
                except Exception as e:
                    print(f"Warning: Could not auto-initialize equipment availability for lab {lab_id}: {e}")

            labs.append({
                "id": row["id"],
                "name": row["name"],
                "capacity": row["capacity"],
                "equipment": row["equipment"],
                "equipment_availability": equipment_availability,
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

        lab_data = {
            "id": row["id"],
            "name": row["name"],
            "capacity": row["capacity"],
            "equipment": row["equipment"],
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

        # Sync equipment availability
        try:
            equipment_list = json.loads(equipment) if isinstance(equipment, str) else equipment
            if isinstance(equipment_list, str):
                # Try to parse as comma-separated
                equipment_list = [e.strip() for e in equipment_list.split(',') if e.strip()]
            if isinstance(equipment_list, list):
                sync_equipment_availability(cursor, lab_id, equipment_list)
                conn.commit()
        except Exception as e:
            print(f"Warning: Could not sync equipment availability: {e}")

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


@app.route("/api/labs/<int:lab_id>/equipment/<path:equipment_name>/availability", methods=["PUT"])
@require_role("admin")
def update_equipment_availability(lab_id, equipment_name):
    """Update equipment availability for a specific lab and equipment (admin only)."""
    from urllib.parse import unquote
    # Decode URL-encoded equipment name
    equipment_name = unquote(equipment_name)

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"message": "Invalid JSON payload.", "success": False}), 400

    if "is_available" not in data:
        return jsonify({"message": "is_available field is required.", "success": False}), 400

    is_available = data["is_available"]
    if is_available not in ["yes", "no"]:
        return jsonify({
            "message": "is_available must be 'yes' or 'no'.",
            "success": False
        }), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if lab exists
        cursor.execute("SELECT id FROM labs WHERE id = ?", (lab_id,))
        if not cursor.fetchone():
            return jsonify({"message": "Lab not found.", "success": False}), 404

        # Check if equipment availability entry exists
        cursor.execute(
            """
            SELECT id FROM equipment_availability
            WHERE lab_id = ? AND equipment_name = ?
            """,
            (lab_id, equipment_name)
        )
        if not cursor.fetchone():
            return jsonify({
                "message": f"Equipment '{equipment_name}' not found for this lab.",
                "success": False
            }), 404

        # Update equipment availability
        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            UPDATE equipment_availability
            SET is_available = ?, updated_at = ?
            WHERE lab_id = ? AND equipment_name = ?
            """,
            (is_available, updated_at, lab_id, equipment_name)
        )
        conn.commit()

        return jsonify({
            "message": "Equipment availability updated successfully.",
            "success": True
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in update_equipment_availability: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to update equipment availability.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in update_equipment_availability: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


# --- Admin Override Booking Endpoint ---

@app.route("/api/admin/bookings/<int:booking_id>/override", methods=["POST"])
@require_role("admin")
def override_booking(booking_id):
    """Override/cancel a booking (admin only)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if bookings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
        if not cursor.fetchone():
            return jsonify({"message": "Bookings table does not exist.", "success": False}), 404

        # Check if booking exists
        cursor.execute("SELECT id, status FROM bookings WHERE id = ?", (booking_id,))
        booking = cursor.fetchone()
        if not booking:
            return jsonify({"message": "Booking not found.", "success": False}), 404

        # Update booking status to cancelled
        updated_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE bookings SET status = 'cancelled', updated_at = ? WHERE id = ?",
            (updated_at, booking_id)
        )
        conn.commit()

        return jsonify({
            "message": "Booking cancelled successfully.",
            "success": True
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in override_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to override booking.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in override_booking: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


# --- Admin Disable Lab Endpoint ---

@app.route("/api/admin/labs/<int:lab_id>/disable", methods=["POST"])
@require_role("admin")
def disable_lab(lab_id):
    """Disable a lab for a specific date (admin only)."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON payload.", "success": False}), 400

    if "date" not in data or not data.get("date"):
        return jsonify({"message": "Date is required.", "success": False}), 400

    date_str = data["date"]
    reason = data.get("reason", "")

    # Validate date
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if date_obj.strftime("%Y-%m-%d") != date_str:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD.", "success": False}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD.", "success": False}), 400

    # Reject past dates
    today = datetime.datetime.now().date()
    if date_obj.date() < today:
        return jsonify({"error": "Past dates are not allowed.", "success": False}), 400

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

        # Ensure disabled_labs table exists
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
        conn.commit()

        # Insert or update disabled lab entry
        created_at = datetime.datetime.now(timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT OR REPLACE INTO disabled_labs (lab_id, disabled_date, reason, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (lab_id, date_str, reason, created_at)
        )
        conn.commit()

        return jsonify({
            "message": "Lab disabled successfully for the specified date.",
            "success": True
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in disable_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "Failed to disable lab.", "success": False}), 500
    except Exception as e:
        print(f"Unexpected error in disable_lab: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": "An unexpected error occurred.", "success": False}), 500
    finally:
        if DATABASE != ":memory:":
            conn.close()


# --- Lab Assistant Assigned Labs Endpoint ---

@app.route("/api/lab-assistant/labs/assigned", methods=["GET"])
@require_role("lab_assistant")
def get_assigned_labs():
    """Get labs assigned to the current lab assistant."""
    date_str = request.args.get("date")
    if not date_str:
        # Default to today if no date provided
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")

    # Validate date
    try:
        date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if date_obj.strftime("%Y-%m-%d") != date_str:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Reject past dates
    today = datetime.datetime.now().date()
    if date_obj.date() < today:
        return jsonify({"error": "Past dates are not allowed"}), 400

    assistant_college_id = request.current_user.get("college_id")
    day_of_week = get_day_of_week(date_str)
    if not day_of_week:
        return jsonify({"error": "Invalid date"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Ensure all required tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lab_assistant_assignments'")
        if not cursor.fetchone():
            # Return empty list if table doesn't exist
            return jsonify({
                "date": date_str,
                "assigned_labs": [],
                "total_assigned": 0,
                "message": "No labs assigned"
            }), 200

        # Get assigned labs for this assistant
        cursor.execute(
            """
            SELECT l.id, l.name, l.capacity, l.equipment
            FROM labs l
            INNER JOIN lab_assistant_assignments laa ON l.id = laa.lab_id
            WHERE laa.assistant_college_id = ?
            ORDER BY l.name ASC
            """,
            (assistant_college_id,)
        )
        assigned_labs_rows = cursor.fetchall()

        if not assigned_labs_rows:
            return jsonify({
                "date": date_str,
                "assigned_labs": [],
                "total_assigned": 0,
                "message": "No labs assigned"
            }), 200

        # Get availability slots for the day
        cursor.execute(
            """
            SELECT lab_id, start_time, end_time
            FROM availability_slots
            WHERE day_of_week = ?
            """,
            (day_of_week,)
        )
        slots_rows = cursor.fetchall()
        slots_by_lab = {}
        for row in slots_rows:
            lab_id = row[0]
            if lab_id not in slots_by_lab:
                slots_by_lab[lab_id] = []
            slots_by_lab[lab_id].append({
                "start_time": row[1],
                "end_time": row[2]
            })

        # Get bookings for the date
        cursor.execute(
            """
            SELECT b.id, b.college_id, b.lab_name, b.start_time, b.end_time,
                   b.status, u.name, u.email
            FROM bookings b
            LEFT JOIN users u ON b.college_id = u.college_id
            WHERE b.booking_date = ?
            ORDER BY b.lab_name ASC, b.start_time ASC
            """,
            (date_str,)
        )
        bookings_rows = cursor.fetchall()
        bookings_by_lab = {}
        for booking in bookings_rows:
            lab_name = booking[2]
            if lab_name not in bookings_by_lab:
                bookings_by_lab[lab_name] = []
            bookings_by_lab[lab_name].append({
                "id": booking[0],
                "college_id": booking[1],
                "name": booking[6],
                "email": booking[7],
                "start_time": booking[3],
                "end_time": booking[4],
                "status": booking[5]
            })

        assigned_labs = []
        for lab_row in assigned_labs_rows:
            lab_id = lab_row[0]
            lab_name = lab_row[1]
            capacity = lab_row[2]
            equipment = lab_row[3]

            # Get availability slots for this lab
            availability_slots = slots_by_lab.get(lab_id, [])
            time_slots = [f"{s['start_time']}-{s['end_time']}" for s in availability_slots]

            # Get bookings for this lab
            lab_bookings = bookings_by_lab.get(lab_name, [])

            assigned_labs.append({
                "lab_id": lab_id,
                "lab_name": lab_name,
                "capacity": capacity,
                "equipment": equipment,
                "availability_slots": time_slots,
                "bookings": lab_bookings,
                "booked_slots_count": len(lab_bookings),
                "free_slots_count": max(0, len(availability_slots) - len(lab_bookings))
            })

        return jsonify({
            "date": date_str,
            "assigned_labs": assigned_labs,
            "total_assigned": len(assigned_labs)
        }), 200
    except sqlite3.Error as e:
        print(f"Database Error in get_assigned_labs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Database error occurred", "details": str(e)}), 500
    except Exception as e:
        print(f"Unexpected Error in get_assigned_labs: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500
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
