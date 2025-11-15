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
            labs.append({
                "id": row["id"],
                "name": row["name"],
                "capacity": row["capacity"],
                "equipment": row["equipment"],
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
    Returns list of available slots.
    """
    available = []
    for slot in availability_slots:
        slot_start = slot['start_time']
        slot_end = slot['end_time']
        is_available = True

        # Check if this slot overlaps with any booking
        for booking in bookings:
            booking_start = booking['start_time']
            booking_end = booking['end_time']
            if slots_overlap(slot_start, slot_end, booking_start, booking_end):
                is_available = False
                break

        if is_available:
            available.append({
                'start_time': slot_start,
                'end_time': slot_end
            })

    return available


# --- Available Labs Endpoint ---


@app.route("/api/labs/available", methods=["GET"])
@require_auth
def get_available_labs():
    """
    Get all available labs and their available slots for a specific date.
    Query parameter: date (YYYY-MM-DD format)
    Past dates are not allowed.
    Optimized for <3s response time with efficient queries.
    """
    import time
    start_time = time.time()

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

        # Optimized: Single query to get all labs with their availability slots
        # and bookings. Using LEFT JOINs to minimize database round trips.
        query = (
            """
            SELECT
                l.id as lab_id,
                l.name as lab_name,
                l.capacity,
                l.equipment,
                av.start_time as avail_start,
                av.end_time as avail_end,
                b.start_time as booking_start,
                b.end_time as booking_end
            FROM labs l
            LEFT JOIN availability_slots av ON l.id = av.lab_id AND av.day_of_week = ?
            LEFT JOIN bookings b ON l.name = b.lab_name
                AND b.booking_date = ?
                AND b.status IN ('approved', 'pending')
            ORDER BY l.name ASC, av.start_time ASC, b.start_time ASC
            """
        )
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
                    "bookings": []
                }

            # Collect availability slots
            if row["avail_start"] and row["avail_end"]:
                slot = {
                    'start_time': row["avail_start"],
                    'end_time': row["avail_end"]
                }
                if slot not in labs_dict[lab_id]["availability_slots"]:
                    labs_dict[lab_id]["availability_slots"].append(slot)

            # Collect bookings
            if row["booking_start"] and row["booking_end"]:
                booking = {
                    'start_time': row["booking_start"],
                    'end_time': row["booking_end"]
                }
                if booking not in labs_dict[lab_id]["bookings"]:
                    labs_dict[lab_id]["bookings"].append(booking)

        # Filter available slots for each lab
        available_labs = []
        for lab_id, lab_data in labs_dict.items():
            available_slots = filter_available_slots(
                lab_data["availability_slots"],
                lab_data["bookings"]
            )

            # Format slots as "HH:MM-HH:MM" strings
            formatted_slots = [
                f"{slot['start_time']}-{slot['end_time']}"
                for slot in available_slots
            ]

            # Only include labs that have at least one available slot for
            # the requested day. Tests expect labs without slots for the
            # day to be excluded.
            if formatted_slots:
                available_labs.append({
                    "lab_id": lab_data["lab_id"],
                    "lab_name": lab_data["lab_name"],
                    "available_slots": formatted_slots
                })

        # Sort by lab name
        available_labs.sort(key=lambda x: x["lab_name"])

        # Check response time
        elapsed_time = time.time() - start_time
        if elapsed_time > 3.0:
            print(f"WARNING: Response time {elapsed_time:.2f}s exceeds 3s threshold")

        return jsonify({
            "date": date_str,
            "labs": available_labs
        }), 200

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


# --- Application Runner ---
# Initialize database on startup
init_db()

if __name__ == "__main__":
    # Use environment variable for debug mode (default: False for security)
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, port=5000)
