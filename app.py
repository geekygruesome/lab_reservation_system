import sqlite3

from flask import Flask, request, jsonify
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
    # 5. role (e.g., 'student', 'admin')
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

# --- Helper Functions (Core Logic) ---


def validate_registration_data(data):
    """
    Validates the data against the user story security rules:
    1. Duplicate email/college ID check (handled separately by database constraints).
    2. Email format validation.
    3. Password complexity (min 8 chars, 1 number, 1 symbol).
    """
    errors = []

    # Check for presence of all required fields
    if not all(
        key in data and data[key] for key in ["college_id", "name", "email", "password", "role"]
    ):
        errors.append("All fields (College ID, Name, Email, Password, Role) are required.")
        return False, errors

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
    data = request.get_json()
    if not data or "college_id" not in data or "password" not in data:
        return jsonify({"message": "College ID and password required."}), 400

    college_id = data["college_id"]
    password = data["password"]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT college_id, password_hash, name, role FROM users WHERE college_id = ?", (college_id,))
    row = cursor.fetchone()
    # Do not leak whether the user exists
    if row is None:
        if DATABASE != ":memory:":
            conn.close()
        return jsonify({"message": "Invalid credentials.", "success": False}), 401

    stored_hash = row["password_hash"]
    if not check_password_hash(stored_hash, password):
        if DATABASE != ":memory:":
            conn.close()
        return jsonify({"message": "Invalid credentials.", "success": False}), 401

    payload = {"college_id": row["college_id"], "role": row["role"], "name": row["name"]}
    token = _generate_token(payload)

    if DATABASE != ":memory:":
        conn.close()

    return jsonify({"token": token, "success": True, "role": row["role"], "name": row["name"]}), 200


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


# --- Application Runner ---
if __name__ == "__main__":
    # Initialize the database before running the app
    # This checks if the file exists and runs the init_db function.
    if not os.path.exists(DATABASE):
        init_db()

    # The init_db function is also decorated to run once on first request
    # but since this is a single file app, running it on startup is best.
    # Use environment variable for debug mode (default: False for security)
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, port=5000)
