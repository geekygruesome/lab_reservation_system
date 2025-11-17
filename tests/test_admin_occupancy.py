#!/usr/bin/env python
"""
Quick validation script to test admin endpoint occupancy metrics.
Run: pytest test_admin_occupancy.py -v -s
"""
import pytest
import datetime
from datetime import timedelta
from werkzeug.security import generate_password_hash
import sqlite3

import app as app_module

@pytest.fixture
def client(monkeypatch):
    """Setup in-memory DB client for testing."""
    app_module.app.config["TESTING"] = True
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Create all tables
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
        CREATE TABLE IF NOT EXISTS labs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            capacity INTEGER NOT NULL,
            equipment TEXT NOT NULL,
            created_at TEXT,
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
            FOREIGN KEY (lab_id) REFERENCES labs(id)
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
        CREATE TABLE IF NOT EXISTS disabled_labs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            disabled_date TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (lab_id) REFERENCES labs(id)
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lab_assistant_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            assistant_college_id TEXT NOT NULL,
            assigned_at TEXT NOT NULL,
            FOREIGN KEY (lab_id) REFERENCES labs(id),
            FOREIGN KEY (assistant_college_id) REFERENCES users(college_id)
        );
    """)
    conn.commit()

    # Monkeypatch to use in-memory DB
    monkeypatch.setattr("app.get_db_connection", lambda: conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")

    with app_module.app.test_client() as test_client:
        yield test_client

    conn.close()

def test_admin_sees_occupancy_metrics(client):
    """Test that admin endpoint returns occupancy metrics and status badges."""
    conn = app_module.get_db_connection()
    cursor = conn.cursor()

    # Create test data
    date_str = (datetime.date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date_str)

    # Create a lab
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment) VALUES (?, ?, ?)",
        ("Physics Lab", 10, "[\"Microscopes\"]"),
    )
    lab_id = cursor.lastrowid

    # Add 2 availability slots
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day, "09:00", "11:00"),
    )
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day, "14:00", "16:00"),
    )

    # Create users
    cursor.execute(
        "INSERT INTO users (college_id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        ("S001", "John Doe", "john@college.edu", generate_password_hash("Pass1!234"), "student"),
    )
    cursor.execute(
        "INSERT INTO users (college_id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        ("A001", "Admin", "admin@college.edu", generate_password_hash("Pass1!234"), "admin"),
    )
    conn.commit()

    # Book one slot
    cursor.execute(
        "INSERT INTO bookings (college_id, lab_name, booking_date, "
        "start_time, end_time, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "S001",
            "Physics Lab",
            date_str,
            "09:00",
            "11:00",
            "approved",
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )
    conn.commit()

    # Login as admin
    login_resp = client.post(
        '/api/login',
        json={"college_id": "A001", "password": "Pass1!234"}
    )
    assert login_resp.status_code == 200
    token = login_resp.get_json()["token"]

    # Get admin view
    resp = client.get(
        f'/api/admin/labs/available?date={date_str}',
        headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 200
    data = resp.get_json()

    # Verify response structure
    assert data['date'] == date_str
    assert data['day_of_week'] == day
    assert data['total_labs'] == 1

    lab = data['labs'][0]

    # Verify occupancy field exists
    assert 'occupancy' in lab
    assert lab['occupancy']['total_slots'] == 2
    # With per-slot capacity, total possible units = slots * capacity
    assert lab['occupancy']['booked'] == 1
    # capacity was set to 10 for the lab, so total_possible = 2 * 10 = 20
    assert lab['occupancy']['free'] == 19
    assert lab['occupancy']['occupancy_label'] == '19/20 free'

    # Verify status badge
    assert lab['status'] == 'Active'
    assert lab['status_badge'] == '🟢'

    # Verify slot details
    assert len(lab['availability_slots']) == 2

    # First slot should reflect per-slot capacity usage
    slot1 = lab['availability_slots'][0]
    assert slot1['time'] == '09:00-11:00'
    assert slot1['booked_count'] == 1
    # capacity 10 -> available units = 9
    assert slot1['available'] == 9
    assert slot1['occupancy_label'] == '9/10 free'

    # Second slot should have full capacity free
    slot2 = lab['availability_slots'][1]
    assert slot2['time'] == '14:00-16:00'
    assert slot2['booked_count'] == 0
    assert slot2['available'] == 10
    assert slot2['occupancy_label'] == '10/10 free'

    print("✅ Admin occupancy metrics test PASSED")

def test_admin_sees_disabled_lab_status(client):
    """Test that disabled labs show correct status badge."""
    conn = app_module.get_db_connection()
    cursor = conn.cursor()

    date_str = (datetime.date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date_str)

    # Create a lab
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment) VALUES (?, ?, ?)",
        ("Chemistry Lab", 15, "[\"Bunsen Burners\"]"),
    )
    lab_id = cursor.lastrowid

    # Add availability
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day, "10:00", "12:00"),
    )

    # Create admin user
    cursor.execute(
        "INSERT INTO users (college_id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        ("A001", "Admin", "admin@college.edu", generate_password_hash("Pass1!234"), "admin"),
    )

    # Disable the lab
    cursor.execute(
        "INSERT INTO disabled_labs (lab_id, disabled_date, reason, created_at) VALUES (?, ?, ?, ?)",
        (lab_id, date_str, "Maintenance", datetime.datetime.now(datetime.timezone.utc).isoformat()),
    )
    conn.commit()

    # Login as admin
    login_resp = client.post(
        '/api/login',
        json={"college_id": "A001", "password": "Pass1!234"}
    )
    token = login_resp.get_json()["token"]

    # Get admin view
    resp = client.get(
        f'/api/admin/labs/available?date={date_str}',
        headers={"Authorization": f"Bearer {token}"}
    )

    assert resp.status_code == 200
    data = resp.get_json()
    lab = data['labs'][0]

    # Verify disabled status
    assert lab['status'] == 'Disabled'
    assert lab['status_badge'] in ['🔴', '\U0001F534']  # Red circle emoji
    assert lab['disabled'] is True
    assert lab['disabled_reason'] == 'Maintenance'

    print("✅ Admin disabled lab status test PASSED")
