import sqlite3
import pytest

from app import app, init_db


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
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
    monkeypatch.setattr("app.get_db_connection", lambda: conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")
    with app.test_client() as client_obj:
        yield client_obj
    conn.close()


def test_registration_and_login_flow(client):
    # Register
    r = client.post(
        "/api/register",
        json={
            "college_id": "X1",
            "name": "X",
            "email": "x@pesu.edu",
            "password": "Pass1!234",
            "role": "student",
        },
    )
    assert r.status_code == 201

    # Login
    login_resp = client.post("/api/login", json={"college_id": "X1", "password": "Pass1!234"})
    assert login_resp.status_code == 200
    token = login_resp.get_json()["token"]

    # Me
    m = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert m.status_code == 200
    assert m.get_json()["college_id"] == "X1"


def test_invalid_json_returns_json(client):
    r = client.post("/api/register", data="notjson", content_type="application/json")
    assert r.status_code == 400
    assert r.get_json() is not None


def test_init_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    monkeypatch.setattr("app.get_db_connection", lambda: conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")
    init_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    assert cur.fetchone() is not None


def test_registration_duplicate_email(client):
    client.post(
        "/api/register",
        json={
            "college_id": "D1",
            "name": "D",
            "email": "dup@pesu.edu",
            "password": "StrongPass1!",
            "role": "student",
        },
    )
    r = client.post(
        "/api/register",
        json={
            "college_id": "D2",
            "name": "D2",
            "email": "dup@pesu.edu",
            "password": "StrongPass1!",
            "role": "student",
        },
    )
    assert r.status_code == 400


def test_registration_duplicate_college_id(client):
    client.post(
        "/api/register",
        json={
            "college_id": "CID1",
            "name": "A",
            "email": "a1@pesu.edu",
            "password": "StrongPass1!",
            "role": "student",
        },
    )
    r = client.post(
        "/api/register",
        json={
            "college_id": "CID1",
            "name": "B",
            "email": "b1@pesu.edu",
            "password": "StrongPass1!",
            "role": "student",
        },
    )
    assert r.status_code == 400


def test_login_invalid_password(client):
    client.post(
        "/api/register",
        json={
            "college_id": "LP1",
            "name": "LP",
            "email": "lp@pesu.edu",
            "password": "Correct1!",
            "role": "student",
        },
    )
    r = client.post("/api/login", json={"college_id": "LP1", "password": "WrongPass"})
    assert r.status_code == 401


def test_login_nonexistent_user(client):
    r = client.post("/api/login", json={"college_id": "NOUSER", "password": "x"})
    assert r.status_code == 401


def test_me_with_invalid_token(client):
    r = client.get("/api/me", headers={"Authorization": "Bearer bad.token.here"})
    assert r.status_code == 401


def test_token_expired(client):
    # craft an expired token
    import jwt as _jwt
    import datetime as _dt
    from datetime import timezone
    exp_time = _dt.datetime.now(timezone.utc) - _dt.timedelta(seconds=10)
    payload = {
        "college_id": "X1",
        "role": "student",
        "name": "X",
        "exp": exp_time,
    }
    token = _jwt.encode(payload, "dev-secret", algorithm="HS256")
    r = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_registration_missing_fields(client):
    # Missing college_id
    r = client.post(
        "/api/register",
        json={
            "name": "X",
            "email": "x@pesu.edu",
            "password": "Pass1!234",
            "role": "student",
        },
    )
    assert r.status_code == 400
    assert "required" in r.get_json()["message"].lower()


def test_registration_invalid_email(client):
    r = client.post(
        "/api/register",
        json={
            "college_id": "IE1",
            "name": "IE",
            "email": "invalid_email",
            "password": "Pass1!234",
            "role": "student",
        },
    )
    assert r.status_code == 400
    assert "email" in r.get_json()["message"].lower()


def test_registration_short_password(client):
    r = client.post(
        "/api/register",
        json={
            "college_id": "SP1",
            "name": "SP",
            "email": "sp@pesu.edu",
            "password": "Short1!",
            "role": "student",
        },
    )
    assert r.status_code == 400
    assert "password" in r.get_json()["message"].lower()


def test_registration_password_no_number(client):
    r = client.post(
        "/api/register",
        json={
            "college_id": "PN1",
            "name": "PN",
            "email": "pn@pesu.edu",
            "password": "NoNumber!abc",
            "role": "student",
        },
    )
    assert r.status_code == 400
    assert "number" in r.get_json()["message"].lower()


def test_registration_password_no_symbol(client):
    r = client.post(
        "/api/register",
        json={
            "college_id": "PS1",
            "name": "PS",
            "email": "ps@pesu.edu",
            "password": "NoSymbol123",
            "role": "student",
        },
    )
    assert r.status_code == 400
    assert "symbol" in r.get_json()["message"].lower()


def test_login_missing_college_id(client):
    r = client.post("/api/login", json={"password": "test"})
    assert r.status_code == 400


def test_login_missing_password(client):
    r = client.post("/api/login", json={"college_id": "C1"})
    assert r.status_code == 400


def test_login_empty_json(client):
    r = client.post("/api/login", json={})
    assert r.status_code == 400


def test_me_missing_auth_header(client):
    r = client.get("/api/me")
    assert r.status_code == 401


def test_me_invalid_bearer_format(client):
    r = client.get("/api/me", headers={"Authorization": "NotBearer token"})
    assert r.status_code == 401


def test_me_with_valid_token(client):
    # Register and login to get a valid token
    client.post(
        "/api/register",
        json={
            "college_id": "ME1",
            "name": "ME",
            "email": "me@pesu.edu",
            "password": "ValidPass1!",
            "role": "admin",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "ME1", "password": "ValidPass1!"})
    token = login_resp.get_json()["token"]
    r = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["college_id"] == "ME1"
    assert r.get_json()["role"] == "admin"
    assert r.get_json()["name"] == "ME"


def test_registration_success_creates_user(client):
    r = client.post(
        "/api/register",
        json={
            "college_id": "RC1",
            "name": "RC",
            "email": "rc@pesu.edu",
            "password": "CreatePass1!",
            "role": "student",
        },
    )
    assert r.status_code == 201
    assert "success" in r.get_json()
    assert r.get_json()["success"] is True


def test_login_response_includes_user_info(client):
    client.post(
        "/api/register",
        json={
            "college_id": "UI1",
            "name": "UserInfo",
            "email": "ui@pesu.edu",
            "password": "InfoPass1!",
            "role": "student",
        },
    )
    r = client.post("/api/login", json={"college_id": "UI1", "password": "InfoPass1!"})
    data = r.get_json()
    assert data["success"] is True
    assert "token" in data
    assert data["role"] == "student"
    assert data["name"] == "UserInfo"


# --- Role-Based Access Tests ---

def test_registration_with_lab_assistant_role(client):
    r = client.post(
        "/api/register",
        json={
            "college_id": "LA1",
            "name": "Lab Assistant",
            "email": "la@pesu.edu",
            "password": "LabPass1!",
            "role": "lab_assistant",
        },
    )
    assert r.status_code == 201
    assert r.get_json()["success"] is True


def test_registration_with_invalid_role(client):
    r = client.post(
        "/api/register",
        json={
            "college_id": "IR1",
            "name": "Invalid Role",
            "email": "ir@pesu.edu",
            "password": "ValidPass1!",
            "role": "invalid_role",
        },
    )
    assert r.status_code == 400
    assert "role" in r.get_json()["message"].lower()


# --- Booking Tests ---

def test_create_booking_requires_auth(client):
    r = client.post(
        "/api/bookings",
        json={
            "lab_name": "Lab A",
            "booking_date": "2024-12-25",
            "start_time": "10:00",
            "end_time": "12:00",
        },
    )
    assert r.status_code == 401


def test_create_booking_success(client):
    # Register and login
    client.post(
        "/api/register",
        json={
            "college_id": "B1",
            "name": "Booker",
            "email": "b1@pesu.edu",
            "password": "BookPass1!",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "B1", "password": "BookPass1!"})
    token = login_resp.get_json()["token"]

    # Create booking
    r = client.post(
        "/api/bookings",
        json={
            "lab_name": "Lab A",
            "booking_date": "2024-12-25",
            "start_time": "10:00",
            "end_time": "12:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    assert r.get_json()["success"] is True
    assert "booking_id" in r.get_json()


def test_create_booking_missing_fields(client):
    # Register and login
    client.post(
        "/api/register",
        json={
            "college_id": "B2",
            "name": "Booker2",
            "email": "b2@pesu.edu",
            "password": "BookPass1!",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "B2", "password": "BookPass1!"})
    token = login_resp.get_json()["token"]

    # Create booking with missing fields
    r = client.post(
        "/api/bookings",
        json={"lab_name": "Lab A"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_create_booking_invalid_date_format(client):
    # Register and login
    client.post(
        "/api/register",
        json={
            "college_id": "B3",
            "name": "Booker3",
            "email": "b3@pesu.edu",
            "password": "BookPass1!",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "B3", "password": "BookPass1!"})
    token = login_resp.get_json()["token"]

    # Create booking with invalid date
    r = client.post(
        "/api/bookings",
        json={
            "lab_name": "Lab A",
            "booking_date": "invalid-date",
            "start_time": "10:00",
            "end_time": "12:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


def test_get_bookings_requires_auth(client):
    r = client.get("/api/bookings")
    assert r.status_code == 401


def test_get_bookings_student_sees_only_own(client):
    # Register student
    client.post(
        "/api/register",
        json={
            "college_id": "S1",
            "name": "Student1",
            "email": "s1@pesu.edu",
            "password": "StudPass1!",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "S1", "password": "StudPass1!"})
    token = login_resp.get_json()["token"]

    # Create booking
    client.post(
        "/api/bookings",
        json={
            "lab_name": "Lab A",
            "booking_date": "2024-12-25",
            "start_time": "10:00",
            "end_time": "12:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    # Get bookings
    r = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.get_json()["bookings"]) == 1
    assert r.get_json()["bookings"][0]["college_id"] == "S1"


def test_get_pending_bookings_requires_admin(client):
    # Register student
    client.post(
        "/api/register",
        json={
            "college_id": "S2",
            "name": "Student2",
            "email": "s2@pesu.edu",
            "password": "StudPass1!",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "S2", "password": "StudPass1!"})
    token = login_resp.get_json()["token"]

    # Try to access admin endpoint
    r = client.get("/api/bookings/pending", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_get_pending_bookings_admin_success(client):
    # Register admin
    client.post(
        "/api/register",
        json={
            "college_id": "A1",
            "name": "Admin1",
            "email": "a1@pesu.edu",
            "password": "AdminPass1!",
            "role": "admin",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "A1", "password": "AdminPass1!"})
    admin_token = login_resp.get_json()["token"]

    # Register student and create booking
    client.post(
        "/api/register",
        json={
            "college_id": "S3",
            "name": "Student3",
            "email": "s3@pesu.edu",
            "password": "StudPass1!",
            "role": "student",
        },
    )
    student_login = client.post("/api/login", json={"college_id": "S3", "password": "StudPass1!"})
    student_token = student_login.get_json()["token"]

    client.post(
        "/api/bookings",
        json={
            "lab_name": "Lab B",
            "booking_date": "2024-12-26",
            "start_time": "14:00",
            "end_time": "16:00",
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )

    # Admin gets pending bookings
    r = client.get("/api/bookings/pending", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert len(r.get_json()["bookings"]) == 1
    assert r.get_json()["bookings"][0]["status"] == "pending"


def test_approve_booking_requires_admin(client):
    # Register student
    client.post(
        "/api/register",
        json={
            "college_id": "S4",
            "name": "Student4",
            "email": "s4@pesu.edu",
            "password": "StudPass1!",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "S4", "password": "StudPass1!"})
    token = login_resp.get_json()["token"]

    # Try to approve (should fail)
    r = client.post("/api/bookings/1/approve", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_approve_booking_admin_success(client):
    # Register admin
    client.post(
        "/api/register",
        json={
            "college_id": "A2",
            "name": "Admin2",
            "email": "a2@pesu.edu",
            "password": "AdminPass1!",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "A2", "password": "AdminPass1!"})
    admin_token = admin_login.get_json()["token"]

    # Register student and create booking
    client.post(
        "/api/register",
        json={
            "college_id": "S5",
            "name": "Student5",
            "email": "s5@pesu.edu",
            "password": "StudPass1!",
            "role": "student",
        },
    )
    student_login = client.post("/api/login", json={"college_id": "S5", "password": "StudPass1!"})
    student_token = student_login.get_json()["token"]

    booking_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Lab C",
            "booking_date": "2024-12-27",
            "start_time": "09:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )
    booking_id = booking_resp.get_json()["booking_id"]

    # Admin approves booking
    r = client.post(
        f"/api/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    # Verify booking is approved
    bookings_resp = client.get("/api/bookings", headers={"Authorization": f"Bearer {admin_token}"})
    bookings = bookings_resp.get_json()["bookings"]
    approved_booking = next((b for b in bookings if b["id"] == booking_id), None)
    assert approved_booking is not None
    assert approved_booking["status"] == "approved"


def test_reject_booking_admin_success(client):
    # Register admin
    client.post(
        "/api/register",
        json={
            "college_id": "A3",
            "name": "Admin3",
            "email": "a3@pesu.edu",
            "password": "AdminPass1!",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "A3", "password": "AdminPass1!"})
    admin_token = admin_login.get_json()["token"]

    # Register student and create booking
    client.post(
        "/api/register",
        json={
            "college_id": "S6",
            "name": "Student6",
            "email": "s6@pesu.edu",
            "password": "StudPass1!",
            "role": "student",
        },
    )
    student_login = client.post("/api/login", json={"college_id": "S6", "password": "StudPass1!"})
    student_token = student_login.get_json()["token"]

    booking_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Lab D",
            "booking_date": "2024-12-28",
            "start_time": "13:00",
            "end_time": "15:00",
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )
    booking_id = booking_resp.get_json()["booking_id"]

    # Admin rejects booking
    r = client.post(
        f"/api/bookings/{booking_id}/reject",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.get_json()["success"] is True

    # Verify booking is rejected
    bookings_resp = client.get("/api/bookings", headers={"Authorization": f"Bearer {admin_token}"})
    bookings = bookings_resp.get_json()["bookings"]
    rejected_booking = next((b for b in bookings if b["id"] == booking_id), None)
    assert rejected_booking is not None
    assert rejected_booking["status"] == "rejected"


def test_approve_nonexistent_booking(client):
    # Register admin
    client.post(
        "/api/register",
        json={
            "college_id": "A4",
            "name": "Admin4",
            "email": "a4@pesu.edu",
            "password": "AdminPass1!",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "A4", "password": "AdminPass1!"})
    admin_token = admin_login.get_json()["token"]

    # Try to approve nonexistent booking
    r = client.post(
        "/api/bookings/99999/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404


def test_get_bookings_admin_sees_all(client):
    # Register admin
    client.post(
        "/api/register",
        json={
            "college_id": "A5",
            "name": "Admin5",
            "email": "a5@pesu.edu",
            "password": "AdminPass1!",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "A5", "password": "AdminPass1!"})
    admin_token = admin_login.get_json()["token"]

    # Register two students
    for i in range(2):
        client.post(
            "/api/register",
            json={
                "college_id": f"ST{i}",
                "name": f"Student{i}",
                "email": f"st{i}@pesu.edu",
                "password": "StudPass1!",
                "role": "student",
            },
        )
        student_login = client.post(
            "/api/login", json={"college_id": f"ST{i}", "password": "StudPass1!"}
        )
        student_token = student_login.get_json()["token"]

        client.post(
            "/api/bookings",
            json={
                "lab_name": f"Lab{i}",
                "booking_date": "2024-12-29",
                "start_time": "10:00",
                "end_time": "12:00",
            },
            headers={"Authorization": f"Bearer {student_token}"},
        )

    # Admin should see all bookings
    r = client.get("/api/bookings", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert len(r.get_json()["bookings"]) == 2


def test_init_db_creates_bookings_table(monkeypatch):
    conn = sqlite3.connect(":memory:")
    monkeypatch.setattr("app.get_db_connection", lambda: conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")
    init_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bookings'")
    assert cur.fetchone() is not None
