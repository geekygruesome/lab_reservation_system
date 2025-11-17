"""
Integration tests for booking endpoints.
Tests the interaction between booking creation, modification, and cancellation.
"""
import sqlite3
import pytest
from datetime import datetime, timedelta, timezone
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


def test_create_modify_cancel_booking_flow(client):
    """Test complete flow: create, modify, then cancel a booking."""
    # Register user
    client.post(
        "/api/register",
        json={
            "college_id": "FLOW1",
            "name": "Flow User",
            "email": "flow@test.com",
            "password": "Flow123!@#",
            "role": "admin",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "FLOW1", "password": "Flow123!@#"})
    token = login_resp.get_json()["token"]
    
    # Create lab
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Flow Lab", 10, "[]", datetime.now().isoformat()),
    )
    conn.commit()
    
    # Create booking
    future_date = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    create_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Flow Lab",
            "booking_date": future_date,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    booking_id = create_resp.get_json()["booking_id"]
    
    # Modify booking
    modify_resp = client.put(
        f"/api/bookings/{booking_id}",
        json={
            "lab_name": "Flow Lab",
            "booking_date": future_date,
            "start_time": "14:00",
            "end_time": "16:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert modify_resp.status_code == 200
    assert modify_resp.get_json()["success"] is True
    
    # Verify modification
    get_resp = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
    bookings = get_resp.get_json()["bookings"]
    modified_booking = next((b for b in bookings if b["id"] == booking_id), None)
    assert modified_booking is not None
    assert modified_booking["start_time"] == "14:00"
    assert modified_booking["end_time"] == "16:00"
    
    # Cancel booking
    cancel_resp = client.delete(
        f"/api/bookings/{booking_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.get_json()["success"] is True
    
    # Verify cancellation
    get_resp2 = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
    bookings2 = get_resp2.get_json()["bookings"]
    cancelled_booking = next((b for b in bookings2 if b["id"] == booking_id), None)
    assert cancelled_booking is None


def test_student_cannot_modify_others_booking(client):
    """Test that students cannot modify other users' bookings."""
    # Register two students
    client.post(
        "/api/register",
        json={
            "college_id": "STU1_MOD",
            "name": "Student One",
            "email": "stu1mod@test.com",
            "password": "Student123!@#",
            "role": "student",
        },
    )
    client.post(
        "/api/register",
        json={
            "college_id": "STU2_MOD",
            "name": "Student Two",
            "email": "stu2mod@test.com",
            "password": "Student123!@#",
            "role": "student",
        },
    )
    
    login1 = client.post("/api/login", json={"college_id": "STU1_MOD", "password": "Student123!@#"})
    token1 = login1.get_json()["token"]
    
    login2 = client.post("/api/login", json={"college_id": "STU2_MOD", "password": "Student123!@#"})
    token2 = login2.get_json()["token"]
    
    # Create lab and availability
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Shared Lab", 10, "[]", datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid
    future_date = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_of_week = app_module.get_day_of_week(future_date)
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, "09:00", "11:00"),
    )
    conn.commit()
    
    # Student 1 creates booking
    booking_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Shared Lab",
            "booking_date": future_date,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {token1}"},
    )
    booking_id = booking_resp.get_json()["booking_id"]
    
    # Student 2 tries to modify Student 1's booking (should fail)
    modify_resp = client.put(
        f"/api/bookings/{booking_id}",
        json={
            "lab_name": "Shared Lab",
            "booking_date": future_date,
            "start_time": "09:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert modify_resp.status_code == 403


def test_available_slots_endpoint_returns_correct_slots(client):
    """Test that available slots endpoint returns correct slots for a lab."""
    # Register user
    client.post(
        "/api/register",
        json={
            "college_id": "SLOTS1",
            "name": "Slots User",
            "email": "slots@test.com",
            "password": "Slots123!@#",
            "role": "student",
        },
    )
    login_resp = client.post("/api/login", json={"college_id": "SLOTS1", "password": "Slots123!@#"})
    token = login_resp.get_json()["token"]
    
    # Create lab and availability slots
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Slots Lab", 5, "[]", datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid
    future_date = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_of_week = app_module.get_day_of_week(future_date)
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, "09:00", "11:00"),
    )
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, "14:00", "16:00"),
    )
    conn.commit()
    
    # Get available slots
    slots_resp = client.get(
        f"/api/labs/Slots Lab/available-slots?date={future_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert slots_resp.status_code == 200
    data = slots_resp.get_json()
    assert data["success"] is True
    assert len(data["available_slots"]) == 2
    assert any(slot["start_time"] == "09:00" and slot["end_time"] == "11:00" for slot in data["available_slots"])
    assert any(slot["start_time"] == "14:00" and slot["end_time"] == "16:00" for slot in data["available_slots"])

