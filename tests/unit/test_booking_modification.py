"""
Unit tests for booking modification logic.
Tests the core business logic for modifying and canceling bookings.
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


def test_modify_booking_student_can_only_use_available_slots(client):
    """Test that students can only modify to available time slots."""
    # Register student
    client.post(
        "/api/register",
        json={
            "college_id": "STU_MOD1",
            "name": "Student Mod",
            "email": "stumod@test.com",
            "password": "Student123!@#",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "STU_MOD1", "password": "Student123!@#"})
    token = login_resp.get_json()["token"]

    # Create lab and availability slot
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Mod Lab", 10, "[]", datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid
    future_date = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_of_week = app_module.get_day_of_week(future_date)
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, "09:00", "11:00"),
    )
    conn.commit()

    # Create booking
    booking_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Mod Lab",
            "booking_date": future_date,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    booking_id = booking_resp.get_json()["booking_id"]

    # Try to modify to invalid time slot (should fail)
    modify_resp = client.put(
        f"/api/bookings/{booking_id}",
        json={
            "lab_name": "Mod Lab",
            "booking_date": future_date,
            "start_time": "14:00",
            "end_time": "16:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert modify_resp.status_code == 400
    assert "available time slots" in modify_resp.get_json()["message"].lower()


def test_modify_booking_admin_can_use_custom_times(client):
    """Test that admin can modify booking to any custom time."""
    # Register admin
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_MOD1",
            "name": "Admin Mod",
            "email": "admmod@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "ADM_MOD1", "password": "Admin123!@#"})
    token = login_resp.get_json()["token"]

    # Create lab
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Admin Mod Lab", 10, "[]", datetime.now().isoformat()),
    )
    conn.commit()

    # Create booking
    future_date = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    booking_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Admin Mod Lab",
            "booking_date": future_date,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    booking_id = booking_resp.get_json()["booking_id"]

    # Modify to custom time (should succeed)
    modify_resp = client.put(
        f"/api/bookings/{booking_id}",
        json={
            "lab_name": "Admin Mod Lab",
            "booking_date": future_date,
            "start_time": "14:00",
            "end_time": "16:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert modify_resp.status_code == 200
    assert modify_resp.get_json()["success"] is True


def test_cancel_booking_removes_from_database(client):
    """Test that canceling a booking removes it from the database."""
    # Register user
    client.post(
        "/api/register",
        json={
            "college_id": "CANCEL1",
            "name": "Cancel User",
            "email": "cancel@test.com",
            "password": "Cancel123!@#",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "CANCEL1", "password": "Cancel123!@#"})
    token = login_resp.get_json()["token"]

    # Create lab and availability slot
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Cancel Lab", 10, "[]", datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid
    future_date = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_of_week = app_module.get_day_of_week(future_date)
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, "09:00", "11:00"),
    )
    conn.commit()

    booking_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Cancel Lab",
            "booking_date": future_date,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert booking_resp.status_code == 201
    booking_id = booking_resp.get_json()["booking_id"]

    # Cancel booking
    cancel_resp = client.delete(
        f"/api/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.get_json()["success"] is True

    # Verify booking is deleted
    cursor.execute("SELECT id FROM bookings WHERE id = ?", (booking_id,))
    assert cursor.fetchone() is None
