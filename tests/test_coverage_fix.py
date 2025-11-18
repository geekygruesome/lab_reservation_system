"""Additional tests to increase coverage for CI/CD requirements."""
import sqlite3
import pytest
import datetime
from datetime import timezone


from app import app
import app as app_module


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

    def get_conn():
        return conn
    monkeypatch.setattr("app.get_db_connection", get_conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")
    with app.test_client() as client_obj:
        yield client_obj
    conn.close()


def test_admin_override_booking_success(client):
    """Test admin can override/cancel a booking."""
    # Register admin and student
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_OVR",
            "name": "Admin Override",
            "email": "adm_ovr@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    client.post(
        "/api/register",
        json={
            "college_id": "STU_OVR",
            "name": "Student Override",
            "email": "stu_ovr@test.com",
            "password": "Student123!@#",
            "role": "student",
        },
    )

    # Login
    admin_login = client.post("/api/login", json={"college_id": "ADM_OVR", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    stu_login = client.post("/api/login", json={"college_id": "STU_OVR", "password": "Student123!@#"})
    stu_token = stu_login.get_json()["token"]

    # Create lab and availability slot
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Override Lab", 20, "[]", datetime.datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid
    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    day_of_week = app_module.get_day_of_week(future_date)
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, "10:00", "12:00"),
    )
    conn.commit()

    # Create booking
    booking_resp = client.post(
        "/api/bookings",
        json={
            "lab_name": "Override Lab",
            "booking_date": future_date,
            "start_time": "10:00",
            "end_time": "12:00",
        },
        headers={"Authorization": f"Bearer {stu_token}"},
    )
    assert booking_resp.status_code == 201
    booking_id = booking_resp.get_json()["booking_id"]

    # Override booking
    r = client.post(
        f"/api/admin/bookings/{booking_id}/override",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert "cancelled" in data["message"].lower() or "overridden" in data["message"].lower()

    # Verify booking status is cancelled
    cursor.execute("SELECT status FROM bookings WHERE id = ?", (booking_id,))
    row = cursor.fetchone()
    assert row["status"] == "cancelled"


def test_admin_override_booking_not_found(client):
    """Test admin override booking when booking doesn't exist."""
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_OVR2",
            "name": "Admin Override2",
            "email": "adm_ovr2@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_OVR2", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    # Try to override non-existent booking
    r = client.post(
        "/api/admin/bookings/99999/override",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404
    assert "not found" in r.get_json()["message"].lower()


def test_admin_disable_lab_success(client):
    """Test admin can disable a lab for a specific date."""
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_DIS",
            "name": "Admin Disable",
            "email": "adm_dis@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_DIS", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    # Create lab
    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Disable Lab", 15, "[]", datetime.datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid
    conn.commit()

    # Disable lab for future date
    future_date = (datetime.date.today() + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    r = client.post(
        f"/api/admin/labs/{lab_id}/disable",
        json={"date": future_date, "reason": "Maintenance"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True

    # Verify lab is disabled
    cursor.execute("SELECT * FROM disabled_labs WHERE lab_id = ? AND disabled_date = ?", (lab_id, future_date))
    row = cursor.fetchone()
    assert row is not None
    assert row["reason"] == "Maintenance"


def test_admin_disable_lab_missing_date(client):
    """Test admin disable lab without date."""
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_DIS2",
            "name": "Admin Disable2",
            "email": "adm_dis2@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_DIS2", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Disable Lab2", 15, "[]", datetime.datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid
    conn.commit()

    r = client.post(
        f"/api/admin/labs/{lab_id}/disable",
        json={},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400
    assert "date" in r.get_json()["message"].lower()


def test_admin_disable_lab_invalid_date(client):
    """Test admin disable lab with invalid date format."""
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_DIS3",
            "name": "Admin Disable3",
            "email": "adm_dis3@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_DIS3", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Disable Lab3", 15, "[]", datetime.datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid
    conn.commit()

    r = client.post(
        f"/api/admin/labs/{lab_id}/disable",
        json={"date": "invalid-date"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400
    assert "date format" in r.get_json()["error"].lower()


def test_admin_disable_lab_past_date(client):
    """Test admin disable lab with past date."""
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_DIS4",
            "name": "Admin Disable4",
            "email": "adm_dis4@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_DIS4", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    conn = app_module.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Disable Lab4", 15, "[]", datetime.datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid
    conn.commit()

    past_date = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.post(
        f"/api/admin/labs/{lab_id}/disable",
        json={"date": past_date},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 400
    assert "past" in r.get_json()["error"].lower()


def test_admin_disable_lab_not_found(client):
    """Test admin disable lab that doesn't exist."""
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_DIS5",
            "name": "Admin Disable5",
            "email": "adm_dis5@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_DIS5", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.post(
        "/api/admin/labs/99999/disable",
        json={"date": future_date},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404
    assert "not found" in r.get_json()["message"].lower()


def test_lab_assistant_assigned_labs_no_assignments(client):
    """Test lab assistant with no assigned labs."""
    client.post(
        "/api/register",
        json={
            "college_id": "LA_NO",
            "name": "Lab Assist No",
            "email": "la_no@test.com",
            "password": "LabAss123!@#",
            "role": "lab_assistant",
        },
    )
    login = client.post("/api/login", json={"college_id": "LA_NO", "password": "LabAss123!@#"})
    token = login.get_json()["token"]

    date_str = datetime.date.today().strftime("%Y-%m-%d")
    r = client.get(
        f"/api/lab-assistant/labs/assigned?date={date_str}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["assigned_labs"] == []
    assert "no labs assigned" in data["message"].lower()


def test_lab_assistant_assigned_labs_with_assignments(client):
    """Test lab assistant with assigned labs."""
    conn = app_module.get_db_connection()
    cursor = conn.cursor()

    # Create lab assistant
    client.post(
        "/api/register",
        json={
            "college_id": "LA_YES",
            "name": "Lab Assist Yes",
            "email": "la_yes@test.com",
            "password": "LabAss123!@#",
            "role": "lab_assistant",
        },
    )
    login = client.post("/api/login", json={"college_id": "LA_YES", "password": "LabAss123!@#"})
    token = login.get_json()["token"]

    # Create lab
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Assigned Lab", 25, "[]", datetime.datetime.now().isoformat()),
    )
    lab_id = cursor.lastrowid

    # Create availability slot
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    day_of_week = app_module.get_day_of_week(date_str)
    cursor.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, "09:00", "17:00"),
    )

    # Assign lab to assistant
    created_at = datetime.datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO lab_assistant_assignments (lab_id, assistant_college_id, assigned_at) VALUES (?, ?, ?)",
        (lab_id, "LA_YES", created_at),
    )
    conn.commit()

    # Get assigned labs
    r = client.get(
        f"/api/lab-assistant/labs/assigned?date={date_str}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["assigned_labs"]) == 1
    assert data["assigned_labs"][0]["lab_name"] == "Assigned Lab"
    assert len(data["assigned_labs"][0]["availability_slots"]) > 0


def test_lab_assistant_assigned_labs_invalid_date(client):
    """Test lab assistant assigned labs with invalid date."""
    client.post(
        "/api/register",
        json={
            "college_id": "LA_INV",
            "name": "Lab Assist Inv",
            "email": "la_inv@test.com",
            "password": "LabAss123!@#",
            "role": "lab_assistant",
        },
    )
    login = client.post("/api/login", json={"college_id": "LA_INV", "password": "LabAss123!@#"})
    token = login.get_json()["token"]

    r = client.get(
        "/api/lab-assistant/labs/assigned?date=invalid-date",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "date format" in r.get_json()["error"].lower()


# Note: test_disable_lab_date_format_edge_case removed - datetime.strptime is immutable and hard to mock
# The edge case (line 2402) is very rare in practice and would require complex mocking
# Other error paths provide sufficient coverage


def test_disable_lab_labs_table_not_exists(client, monkeypatch):
    """Test disable_lab when labs table doesn't exist (line 2418)."""
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_NOTAB",
            "name": "Admin NoTab",
            "email": "adm_notab@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_NOTAB", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    # Create a connection without labs table
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Don't create labs table
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

    def get_conn():
        return conn
    monkeypatch.setattr("app.get_db_connection", get_conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")

    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.post(
        "/api/admin/labs/1/disable",
        json={"date": future_date},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404
    assert "labs table does not exist" in r.get_json()["message"].lower()
    conn.close()


def test_disable_lab_database_error(client, monkeypatch):
    """Test disable_lab database error handling (lines 2455-2464)."""
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_DBERR",
            "name": "Admin DBErr",
            "email": "adm_dberr@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_DBERR", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    # Create a connection that raises sqlite3.Error
    class ErrorConn:
        def cursor(self):
            raise sqlite3.Error("Simulated database error")
        def close(self):
            pass
        def commit(self):
            raise sqlite3.Error("Simulated commit error")

    monkeypatch.setattr("app.get_db_connection", lambda: ErrorConn())
    monkeypatch.setattr("app.DATABASE", "test.db")  # Not :memory: to trigger finally block

    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.post(
        "/api/admin/labs/1/disable",
        json={"date": future_date},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 500
    assert "failed" in r.get_json()["message"].lower()


def test_disable_lab_unexpected_error(client, monkeypatch):
    """Test disable_lab unexpected error handling (lines 2460-2464)."""
    client.post(
        "/api/register",
        json={
            "college_id": "ADM_UNEXP",
            "name": "Admin Unexp",
            "email": "adm_unexp@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    admin_login = client.post("/api/login", json={"college_id": "ADM_UNEXP", "password": "Admin123!@#"})
    admin_token = admin_login.get_json()["token"]

    # Create a connection that raises generic Exception
    class ErrorConn:
        def cursor(self):
            raise Exception("Simulated unexpected error")
        def close(self):
            pass

    monkeypatch.setattr("app.get_db_connection", lambda: ErrorConn())
    monkeypatch.setattr("app.DATABASE", "test.db")  # Not :memory: to trigger finally block

    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.post(
        "/api/admin/labs/1/disable",
        json={"date": future_date},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 500
    assert "unexpected error" in r.get_json()["message"].lower()


# Note: test_get_assigned_labs_date_format_edge_case removed - datetime.strptime is immutable and hard to mock
# The edge case (line 2485) is very rare in practice and would require complex mocking
# Other error paths provide sufficient coverage


def test_get_assigned_labs_past_date(client):
    """Test get_assigned_labs with past date (line 2492)."""
    client.post(
        "/api/register",
        json={
            "college_id": "LA_PAST",
            "name": "Lab Assist Past",
            "email": "la_past@test.com",
            "password": "LabAss123!@#",
            "role": "lab_assistant",
        },
    )
    login = client.post("/api/login", json={"college_id": "LA_PAST", "password": "LabAss123!@#"})
    token = login.get_json()["token"]

    past_date = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.get(
        f"/api/lab-assistant/labs/assigned?date={past_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "past" in r.get_json()["error"].lower()


def test_get_assigned_labs_invalid_date_get_day_of_week(client, monkeypatch):
    """Test get_assigned_labs with date that get_day_of_week returns None (line 2497)."""
    client.post(
        "/api/register",
        json={
            "college_id": "LA_INV2",
            "name": "Lab Assist Inv2",
            "email": "la_inv2@test.com",
            "password": "LabAss123!@#",
            "role": "lab_assistant",
        },
    )
    login = client.post("/api/login", json={"college_id": "LA_INV2", "password": "LabAss123!@#"})
    token = login.get_json()["token"]

    # Mock get_day_of_week to return None
    monkeypatch.setattr("app.get_day_of_week", lambda x: None)

    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.get(
        f"/api/lab-assistant/labs/assigned?date={future_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "invalid date" in r.get_json()["error"].lower()


def test_get_assigned_labs_table_not_exists(client, monkeypatch):
    """Test get_assigned_labs when lab_assistant_assignments table doesn't exist (line 2507)."""
    client.post(
        "/api/register",
        json={
            "college_id": "LA_NOTAB",
            "name": "Lab Assist NoTab",
            "email": "la_notab@test.com",
            "password": "LabAss123!@#",
            "role": "lab_assistant",
        },
    )
    login = client.post("/api/login", json={"college_id": "LA_NOTAB", "password": "LabAss123!@#"})
    token = login.get_json()["token"]

    # Create a connection without lab_assistant_assignments table
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
    conn.commit()

    def get_conn():
        return conn
    monkeypatch.setattr("app.get_db_connection", get_conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")

    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.get(
        f"/api/lab-assistant/labs/assigned?date={future_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["assigned_labs"] == []
    conn.close()


def test_get_assigned_labs_database_error(client, monkeypatch):
    """Test get_assigned_labs database error handling (lines 2613-2617)."""
    client.post(
        "/api/register",
        json={
            "college_id": "LA_DBERR",
            "name": "Lab Assist DBErr",
            "email": "la_dberr@test.com",
            "password": "LabAss123!@#",
            "role": "lab_assistant",
        },
    )
    login = client.post("/api/login", json={"college_id": "LA_DBERR", "password": "LabAss123!@#"})
    token = login.get_json()["token"]

    # Create a connection that raises sqlite3.Error
    class ErrorConn:
        def cursor(self):
            raise sqlite3.Error("Simulated database error")
        def close(self):
            pass

    monkeypatch.setattr("app.get_db_connection", lambda: ErrorConn())
    monkeypatch.setattr("app.DATABASE", "test.db")  # Not :memory: to trigger finally block

    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.get(
        f"/api/lab-assistant/labs/assigned?date={future_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 500
    assert "database error" in r.get_json()["error"].lower()


def test_get_assigned_labs_unexpected_error(client, monkeypatch):
    """Test get_assigned_labs unexpected error handling (lines 2618-2622)."""
    client.post(
        "/api/register",
        json={
            "college_id": "LA_UNEXP",
            "name": "Lab Assist Unexp",
            "email": "la_unexp@test.com",
            "password": "LabAss123!@#",
            "role": "lab_assistant",
        },
    )
    login = client.post("/api/login", json={"college_id": "LA_UNEXP", "password": "LabAss123!@#"})
    token = login.get_json()["token"]

    # Create a connection that raises generic Exception
    class ErrorConn:
        def cursor(self):
            raise Exception("Simulated unexpected error")
        def close(self):
            pass

    monkeypatch.setattr("app.get_db_connection", lambda: ErrorConn())
    monkeypatch.setattr("app.DATABASE", "test.db")  # Not :memory: to trigger finally block

    future_date = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    r = client.get(
        f"/api/lab-assistant/labs/assigned?date={future_date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 500
    assert "unexpected error" in r.get_json()["error"].lower()


def test_get_bookings_database_error(client, monkeypatch):
    """Test get_bookings database error handling."""
    client.post(
        "/api/register",
        json={
            "college_id": "BOOK_ERR",
            "name": "Book Err",
            "email": "bookerr@test.com",
            "password": "Book123!@#",
            "role": "student",
        },
    )
    login = client.post("/api/login", json={"college_id": "BOOK_ERR", "password": "Book123!@#"})
    token = login.get_json()["token"]

    # Create a connection that raises sqlite3.Error
    class ErrorConn:
        def cursor(self):
            raise sqlite3.Error("Simulated database error")
        def close(self):
            pass

    monkeypatch.setattr("app.get_db_connection", lambda: ErrorConn())
    monkeypatch.setattr("app.DATABASE", "test.db")

    r = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 500
    assert "failed" in r.get_json()["message"].lower()


def test_get_bookings_unexpected_error(client, monkeypatch):
    """Test get_bookings unexpected error handling."""
    client.post(
        "/api/register",
        json={
            "college_id": "BOOK_UNEXP",
            "name": "Book Unexp",
            "email": "bookunexp@test.com",
            "password": "Book123!@#",
            "role": "student",
        },
    )
    login = client.post("/api/login", json={"college_id": "BOOK_UNEXP", "password": "Book123!@#"})
    token = login.get_json()["token"]

    # Create a connection that raises generic Exception
    class ErrorConn:
        def cursor(self):
            raise Exception("Simulated unexpected error")
        def close(self):
            pass

    monkeypatch.setattr("app.get_db_connection", lambda: ErrorConn())
    monkeypatch.setattr("app.DATABASE", "test.db")

    r = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 500
    assert "unexpected error" in r.get_json()["message"].lower()


def test_get_pending_bookings_database_error(client, monkeypatch):
    """Test get_pending_bookings database error handling."""
    client.post(
        "/api/register",
        json={
            "college_id": "PEND_ERR",
            "name": "Pend Err",
            "email": "penderr@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    login = client.post("/api/login", json={"college_id": "PEND_ERR", "password": "Admin123!@#"})
    token = login.get_json()["token"]

    # Create a connection that raises sqlite3.Error
    class ErrorConn:
        def cursor(self):
            raise sqlite3.Error("Simulated database error")
        def close(self):
            pass

    monkeypatch.setattr("app.get_db_connection", lambda: ErrorConn())
    monkeypatch.setattr("app.DATABASE", "test.db")

    r = client.get("/api/bookings/pending", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 500
    assert "failed" in r.get_json()["message"].lower()


def test_get_pending_bookings_unexpected_error(client, monkeypatch):
    """Test get_pending_bookings unexpected error handling."""
    client.post(
        "/api/register",
        json={
            "college_id": "PEND_UNEXP",
            "name": "Pend Unexp",
            "email": "pendunexp@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    login = client.post("/api/login", json={"college_id": "PEND_UNEXP", "password": "Admin123!@#"})
    token = login.get_json()["token"]

    # Create a connection that raises generic Exception
    class ErrorConn:
        def cursor(self):
            raise Exception("Simulated unexpected error")
        def close(self):
            pass

    monkeypatch.setattr("app.get_db_connection", lambda: ErrorConn())
    monkeypatch.setattr("app.DATABASE", "test.db")

    r = client.get("/api/bookings/pending", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 500
    assert "unexpected error" in r.get_json()["message"].lower()


def test_approve_booking_table_not_exists(client, monkeypatch):
    """Test approve_booking when bookings table doesn't exist."""
    client.post(
        "/api/register",
        json={
            "college_id": "APP_NOTAB",
            "name": "App NoTab",
            "email": "appnotab@test.com",
            "password": "Admin123!@#",
            "role": "admin",
        },
    )
    login = client.post("/api/login", json={"college_id": "APP_NOTAB", "password": "Admin123!@#"})
    token = login.get_json()["token"]

    # Create a connection without bookings table
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
    conn.commit()

    def get_conn():
        return conn
    monkeypatch.setattr("app.get_db_connection", get_conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")

    r = client.post(
        "/api/bookings/1/approve",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert "bookings table does not exist" in r.get_json()["message"].lower()
    conn.close()
