import sqlite3
import pytest
from app import app, _generate_token


def raise_sqlite_error():
    # Return a fake connection whose cursor() raises sqlite3.Error when used.
    class FakeConn:
        def cursor(self):
            raise sqlite3.Error("simulated db error")

        def close(self):
            pass
    return FakeConn()


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
    conn.commit()
    monkeypatch.setattr("app.get_db_connection", lambda: conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")
    with app.test_client() as client_obj:
        yield client_obj
    conn.close()


def test_create_booking_db_error(client, monkeypatch):
    # Force DB connection to raise sqlite error to hit exception branch
    monkeypatch.setattr("app.get_db_connection", raise_sqlite_error)
    token = _generate_token({"college_id": "ERR1", "role": "student", "name": "Err"})
    resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Lab X",
            "booking_date": "2025-01-01",
            "start_time": "10:00",
            "end_time": "11:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 500
    assert resp.get_json().get("success") is False


def test_check_availability_db_error(client, monkeypatch):
    # The /api/bookings/check endpoint doesn't exist, so this test should be removed or updated
    # Using available-slots endpoint instead which does exist
    # Need to create lab first, then mock DB error after date validation passes
    from datetime import datetime, timedelta
    import app as app_module

    # Create lab first before mocking DB error
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("TestLab", 10, "[]", datetime.now().isoformat()),
    )
    conn.commit()

    # Now mock DB error - this will trigger after date validation
    monkeypatch.setattr("app.get_db_connection", raise_sqlite_error)
    token = _generate_token({"college_id": "ERR2", "role": "student", "name": "Err"})
    future_date = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    resp = client.get(
        f"/api/labs/TestLab/available-slots?date={future_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 500
    assert resp.get_json().get("success") is False


def test_get_labs_db_error(client, monkeypatch):
    monkeypatch.setattr("app.get_db_connection", raise_sqlite_error)
    token = _generate_token({"college_id": "ERR3", "role": "student", "name": "Err"})
    resp = client.get("/api/labs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 500
    assert resp.get_json().get("success") is False


def test_update_equipment_availability_db_error(client, monkeypatch):
    # The endpoint requires admin role, not faculty
    monkeypatch.setattr("app.get_db_connection", raise_sqlite_error)
    token = _generate_token({"college_id": "ERR4", "role": "admin", "name": "Err"})
    resp = client.put(
        "/api/labs/1/equipment/Computer/availability",
        json={"is_available": "no"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 500
    assert resp.get_json().get("success") is False


def test_admin_available_labs_db_error(client, monkeypatch):
    monkeypatch.setattr("app.get_db_connection", raise_sqlite_error)
    token = _generate_token({"college_id": "ERR5", "role": "admin", "name": "Err"})
    resp = client.get("/api/admin/labs/available?date=2026-01-01", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 500
    assert resp.get_json().get("error") is not None
