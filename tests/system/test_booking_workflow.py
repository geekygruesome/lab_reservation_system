"""
System/End-to-End tests for complete booking workflow.
Tests the entire user journey from booking creation to modification and cancellation.
"""
import sqlite3
import pytest
from datetime import datetime, timedelta
import app as app_module


@pytest.fixture
def client(monkeypatch):
    """Create a test client with in-memory database."""
    app_module.app.config["TESTING"] = True
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Create all required tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            college_id TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );
    """)
    cursor.execute("""
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
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS labs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            capacity INTEGER NOT NULL,
            equipment TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS availability_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    monkeypatch.setattr("app.get_db_connection", lambda: conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")
    with app_module.app.test_client() as client_obj:
        yield client_obj
    conn.close()


def test_complete_student_booking_journey(client):
    """Test complete student journey: view available slots, book, modify, cancel."""
    # Register student
    client.post(
        "/api/register",
        json={
            "college_id": "JOURNEY1",
            "name": "Journey Student",
            "email": "journey@test.com",
            "password": "Journey123!@#",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "JOURNEY1", "password": "Journey123!@#"})
    token = login_resp.get_json()["token"]

    # Admin creates lab with availability
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_JOUR",
            "name": "Admin Journey",
            "email": "admjour@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_JOUR", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    # Create lab
    create_lab_resp = client.post(
        "/api/labs",
        json={
            "name": "Journey Lab",
            "capacity": 10,
            "equipment": ["Computer", "Projector"],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_lab_resp.status_code == 201

    # Create availability slot (admin/faculty would do this)
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM labs WHERE name = 'Journey Lab'")
    lab_id = cursor.fetchone()[0]
    future_date = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_of_week = app_module.get_day_of_week(future_date)
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, "09:00", "11:00"),
    )
    conn.commit()

    # Student views available slots
    slots_resp = client.get(
        f"/api/labs/Journey Lab/available-slots?date={future_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert slots_resp.status_code == 200
    slots_data = slots_resp.get_json()
    assert len(slots_data["available_slots"]) > 0

    # Student creates booking using available slot
    booking_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Journey Lab",
            "booking_date": future_date,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert booking_resp.status_code == 201
    booking_id = booking_resp.get_json()["booking_id"]

    # Admin approves booking
    approve_resp = client.post(
        f"/api/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert approve_resp.status_code == 200

    # Student views their bookings
    bookings_resp = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
    assert bookings_resp.status_code == 200
    bookings = bookings_resp.get_json()["bookings"]
    assert len(bookings) == 1
    assert bookings[0]["status"] == "approved"

    # Student modifies booking (to another available slot)
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, "14:00", "16:00"),
    )
    conn.commit()

    modify_resp = client.put(
        f"/api/bookings/{booking_id}",
        json={
            "lab_name": "Journey Lab",
            "booking_date": future_date,
            "start_time": "14:00",
            "end_time": "16:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert modify_resp.status_code == 200

    # Verify modification
    bookings_resp2 = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
    modified_booking = next((b for b in bookings_resp2.get_json()["bookings"] if b["id"] == booking_id), None)
    assert modified_booking["start_time"] == "14:00"
    assert modified_booking["end_time"] == "16:00"

    # Student cancels booking
    cancel_resp = client.delete(
        f"/api/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancel_resp.status_code == 200

    # Verify cancellation
    bookings_resp3 = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
    assert len(bookings_resp3.get_json()["bookings"]) == 0


def test_faculty_admin_modify_reflects_in_available_labs(client):
    """Test that when faculty/admin modifies booking, it reflects in available labs view."""
    # Register faculty
    client.post(
        "/api/register",
        json={
            "college_id": "FAC_MOD",
            "name": "Faculty Mod",
            "email": "facmod@test.com",
            "password": "Faculty123!@#",
            "role": "faculty",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "FAC_MOD", "password": "Faculty123!@#"})
    token = login_resp.get_json()["token"]

    # Create lab
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Faculty Lab", 10, "[]", datetime.now().isoformat()),
    )
    conn.commit()

    # Create booking
    future_date = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    booking_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Faculty Lab",
            "booking_date": future_date,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    booking_id = booking_resp.get_json()["booking_id"]

    # Approve booking (as admin)
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_FAC",
            "name": "Admin Fac",
            "email": "admfac@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_FAC", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    client.post(
        f"/api/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # View available labs (should show the booking)
    labs_resp = client.get(
        f"/api/labs/available?date={future_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert labs_resp.status_code == 200
    labs_data = labs_resp.get_json()
    faculty_lab = next((lab for lab in labs_data["labs"] if lab["lab_name"] == "Faculty Lab"), None)
    assert faculty_lab is not None
    assert "09:00-11:00" in faculty_lab["time_slots"]

    # Faculty modifies booking
    modify_resp = client.put(
        f"/api/bookings/{booking_id}",
        json={
            "lab_name": "Faculty Lab",
            "booking_date": future_date,
            "start_time": "14:00",
            "end_time": "16:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert modify_resp.status_code == 200

    # View available labs again (should show updated time)
    labs_resp2 = client.get(
        f"/api/labs/available?date={future_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    labs_data2 = labs_resp2.get_json()
    faculty_lab2 = next((lab for lab in labs_data2["labs"] if lab["lab_name"] == "Faculty Lab"), None)
    assert faculty_lab2 is not None
    assert "14:00-16:00" in faculty_lab2["time_slots"]
    assert "09:00-11:00" not in faculty_lab2["time_slots"]
