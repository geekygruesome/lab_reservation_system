import sqlite3
import pytest
import datetime
from datetime import timezone, timedelta
from werkzeug.security import generate_password_hash

import app as app_module

@pytest.fixture
def client(monkeypatch):
    app_module.app.config["TESTING"] = True
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # create minimal tables used in these tests
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
        CREATE TABLE IF NOT EXISTS disabled_labs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            disabled_date TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL
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
    conn.commit()
    monkeypatch.setattr("app.get_db_connection", lambda: conn)
    monkeypatch.setattr("app.DATABASE", ":memory:")
    with app_module.app.test_client() as client_obj:
        yield client_obj
    conn.close()

def _create_user(conn, college_id, name, email, role, password='Pass1!234'):
    cur = conn.cursor()
    password_hash = generate_password_hash(password)
    cur.execute(
        "INSERT INTO users (college_id, name, email, password_hash, role) "
        "VALUES (?, ?, ?, ?, ?)",
        (college_id, name, email, password_hash, role),
    )
    conn.commit()

def _create_lab(conn, name, capacity=10, equipment='[]'):
    cur = conn.cursor()
    created_at = datetime.datetime.now(timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) "
        "VALUES (?, ?, ?, ?)",
        (name, capacity, equipment, created_at),
    )
    conn.commit()
    return cur.lastrowid

def _create_availability(conn, lab_id, day_of_week, start_time, end_time):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO availability_slots (lab_id, day_of_week, start_time, end_time) "
        "VALUES (?, ?, ?, ?)",
        (lab_id, day_of_week, start_time, end_time),
    )
    conn.commit()

def _create_booking(conn, college_id, lab_name, booking_date, start_time, end_time, status='approved'):
    cur = conn.cursor()
    created_at = datetime.datetime.now(timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO bookings (college_id, lab_name, booking_date, start_time, end_time, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (college_id, lab_name, booking_date, start_time, end_time, status, created_at),
    )
    conn.commit()
    return cur.lastrowid

def test_student_view_valid_date(client):
    conn = app_module.get_db_connection()
    # create a student
    _create_user(conn, 'S1', 'Student One', 's1@u.edu', 'student')
    # create a lab and availability for tomorrow
    date = (datetime.date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date)
    lab_id = _create_lab(conn, 'Physics', 40, '[]')
    _create_availability(conn, lab_id, day, '09:00', '11:00')

    # login by crafting a token (reuse app._generate_token if available)
    # simpler: register and login via API endpoints
    client.post(
        '/api/register',
        json={
            'college_id': 'T1',
            'name': 'T',
            'email': 't@u.edu',
            'password': 'Pass1!234',
            'role': 'student',
        },
    )
    login = client.post(
        '/api/login',
        json={
            'college_id': 'T1',
            'password': 'Pass1!234',
        },
    )
    token = login.get_json()['token']

    resp = client.get(
        f'/api/labs/available?date={date}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'labs' in data
    assert any(lab['lab_name'] == 'Physics' for lab in data['labs'])

def test_reject_past_date(client):
    client.post(
        '/api/register',
        json={
            'college_id': 'P1',
            'name': 'P',
            'email': 'p@u.edu',
            'password': 'Pass1!234',
            'role': 'student',
        },
    )
    login = client.post(
        '/api/login',
        json={
            'college_id': 'P1',
            'password': 'Pass1!234',
        },
    )
    token = login.get_json()['token']
    yesterday = (datetime.date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    r = client.get(
        f'/api/labs/available?date={yesterday}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert r.status_code == 400

def test_lab_with_full_bookings(client):
    conn = app_module.get_db_connection()
    _create_user(conn, 'S2', 'Stu2', 's2@u.edu', 'student')
    date = (datetime.date.today() + timedelta(days=2)).strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date)
    lab_id = _create_lab(conn, 'Chemistry', 1, '[]')
    # Delete automatically created slots first
    cursor = conn.cursor()
    cursor.execute("DELETE FROM availability_slots WHERE lab_id = ? AND day_of_week = ?", (lab_id, day))
    conn.commit()
    _create_availability(conn, lab_id, day, '09:00', '11:00')
    # create booking that overlaps
    _create_booking(conn, 'S2', 'Chemistry', date, '09:30', '10:30', status='approved')

    client.post(
        '/api/register',
        json={
            'college_id': 'A2',
            'name': 'A2',
            'email': 'a2@u.edu',
            'password': 'Pass1!234',
            'role': 'student',
        },
    )
    login = client.post(
        '/api/login',
        json={
            'college_id': 'A2',
            'password': 'Pass1!234',
        },
    )
    token = login.get_json()['token']

    resp = client.get(
        f'/api/labs/available?date={date}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    # Chemistry should be visible because it has slots configured (even if fully booked)
    # Students can see labs with configured slots to know they exist
    chemistry_lab = next((lab for lab in data['labs'] if lab['lab_name'] == 'Chemistry'), None)
    assert chemistry_lab is not None, "Lab with configured slots should be visible to students even if fully booked"
    # But the slot should show as fully booked
    assert chemistry_lab.get('occupancy', {}).get('free', 1) == 0, "Lab should show 0 free slots"

def test_admin_view_and_override_and_disable(client):
    conn = app_module.get_db_connection()
    # create admin and student
    _create_user(conn, 'ADM1', 'Admin', 'adm@u.edu', 'admin')
    _create_user(conn, 'ST1', 'Student', 'st@u.edu', 'student')

    date = (datetime.date.today() + timedelta(days=3)).strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date)
    lab_id = _create_lab(conn, 'Biology', 25, '[]')
    _create_availability(conn, lab_id, day, '10:00', '12:00')
    booking_id = _create_booking(conn, 'ST1', 'Biology', date, '10:00', '11:00', status='approved')

    # admin login
    client.post(
        '/api/register',
        json={
            'college_id': 'ADMREG',
            'name': 'ADMREG',
            'email': 'admreg@u.edu',
            'password': 'Pass1!234',
            'role': 'admin',
        },
    )
    login = client.post(
        '/api/login',
        json={'college_id': 'ADMREG', 'password': 'Pass1!234'},
    )
    admin_token = login.get_json()['token']

    # view admin labs
    r = client.get(
        f'/api/admin/labs/available?date={date}',
        headers={'Authorization': f'Bearer {admin_token}'},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert any(lab['lab_name'] == 'Biology' for lab in data['labs'])
    bio = [lab for lab in data['labs'] if lab['lab_name'] == 'Biology'][0]
    assert len(bio['bookings']) == 1

    # override booking
    r2 = client.post(
        f'/api/admin/bookings/{booking_id}/override',
        headers={'Authorization': f'Bearer {admin_token}'},
    )
    assert r2.status_code == 200

    # after override, booking status should be cancelled when fetched via admin endpoint
    r3 = client.get(
        f'/api/admin/labs/available?date={date}',
        headers={'Authorization': f'Bearer {admin_token}'},
    )
    bio2 = [lab for lab in r3.get_json()['labs'] if lab['lab_name'] == 'Biology'][0]
    assert (
        bio2['bookings'][0]['status'] in ('cancelled', 'overridden')
        or bio2['bookings'][0]['status'] == 'cancelled'
    )

    # disable lab for date
    r4 = client.post(
        f'/api/admin/labs/{lab_id}/disable',
        headers={'Authorization': f'Bearer {admin_token}'},
        json={'date': date},
    )
    assert r4.status_code == 200

    # student view should not include the disabled lab
    client.post(
        '/api/register',
        json={
            'college_id': 'STREG',
            'name': 'STREG',
            'email': 'streg@u.edu',
            'password': 'Pass1!234',
            'role': 'student',
        },
    )
    login2 = client.post(
        '/api/login',
        json={'college_id': 'STREG', 'password': 'Pass1!234'},
    )
    token2 = login2.get_json()['token']
    rs = client.get(
        f'/api/labs/available?date={date}',
        headers={'Authorization': f'Bearer {token2}'},
    )
    assert rs.status_code == 200
    assert not any(lab['lab_name'] == 'Biology' for lab in rs.get_json()['labs'])

def test_admin_endpoint_requires_admin_role(client):
    # register as student and try to access admin endpoint
    client.post(
        '/api/register',
        json={
            'college_id': 'N1',
            'name': 'N',
            'email': 'n@u.edu',
            'password': 'Pass1!234',
            'role': 'student',
        },
    )
    login = client.post(
        '/api/login',
        json={'college_id': 'N1', 'password': 'Pass1!234'},
    )
    token = login.get_json()['token']
    date = (datetime.date.today() + timedelta(days=4)).strftime('%Y-%m-%d')
    r = client.get(
        f'/api/admin/labs/available?date={date}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert r.status_code == 403

def test_lab_assistant_view_assigned_labs(client):
    """Lab assistant should only see labs assigned to them."""
    conn = app_module.get_db_connection()

    # Create two labs
    date_str = datetime.date.today().strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date_str)
    lab1_id = _create_lab(conn, 'Physics', 40, '["Telescope", "Prism"]')
    lab2_id = _create_lab(conn, 'Chemistry', 30, '["Bunsen Burner"]')

    # Create availability slots
    _create_availability(conn, lab1_id, day, '09:00', '11:00')
    _create_availability(conn, lab2_id, day, '14:00', '16:00')

    # Register and login as lab assistant first
    client.post(
        '/api/register',
        json={
            'college_id': 'LA1',
            'name': 'Lab Assist One',
            'email': 'la1@u.edu',
            'password': 'Pass1!234',
            'role': 'lab_assistant',
        },
    )
    login_r = client.post(
        '/api/login',
        json={'college_id': 'LA1', 'password': 'Pass1!234'},
    )
    token = login_r.get_json()['token']

    # Now assign only lab1 to the assistant (after user exists)
    cur = conn.cursor()
    created_at = datetime.datetime.now(timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO lab_assistant_assignments"
        " (lab_id, assistant_college_id, assigned_at)"
        " VALUES (?, ?, ?)",
        (lab1_id, 'LA1', created_at),
    )
    conn.commit()

    # Fetch assigned labs
    r = client.get(
        f'/api/lab-assistant/labs/assigned?date={date_str}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert 'assigned_labs' in data
    assert len(data['assigned_labs']) == 1
    assert data['assigned_labs'][0]['lab_name'] == 'Physics'

def test_lab_assistant_sees_all_slots(client):
    """Lab assistant should see both free and booked slots for their labs."""
    conn = app_module.get_db_connection()

    # Create student for booking
    _create_user(conn, 'S2', 'Student Two', 's2@u.edu', 'student')

    # Create a lab with availability
    date_str = datetime.date.today().strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date_str)
    lab_id = _create_lab(conn, 'Biology', 25, '["Microscope"]')
    _create_availability(conn, lab_id, day, '09:00', '17:00')

    # Create a booking
    _create_booking(conn, 'S2', 'Biology', date_str, '10:00', '12:00', 'approved')

    # Register and login as lab assistant
    client.post(
        '/api/register',
        json={
            'college_id': 'LA2',
            'name': 'Lab Assist Two',
            'email': 'la2@u.edu',
            'password': 'Pass1!234',
            'role': 'lab_assistant',
        },
    )
    login_r = client.post(
        '/api/login',
        json={'college_id': 'LA2', 'password': 'Pass1!234'},
    )
    token = login_r.get_json()['token']

    # Assign lab to assistant
    cur = conn.cursor()
    created_at = datetime.datetime.now(timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO lab_assistant_assignments"
        " (lab_id, assistant_college_id, assigned_at)"
        " VALUES (?, ?, ?)",
        (lab_id, 'LA2', created_at),
    )
    conn.commit()

    # Fetch assigned labs
    r = client.get(
        f'/api/lab-assistant/labs/assigned?date={date_str}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert r.status_code == 200
    data = r.get_json()
    lab = data['assigned_labs'][0]
    # Should show availability slots
    assert lab['availability_slots']
    # Should show bookings (so they know who is coming)
    assert lab['bookings']
    assert len(lab['bookings']) == 1
    assert lab['bookings'][0]['college_id'] == 'S2'

def test_lab_assistant_default_to_today(client):
    """If no date provided, lab assistant should get today's assigned labs."""
    conn = app_module.get_db_connection()

    # Create a lab
    date_str = datetime.date.today().strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date_str)
    lab_id = _create_lab(conn, 'Biotechnology', 35, '["Centrifuge"]')
    _create_availability(conn, lab_id, day, '08:00', '18:00')

    # Register and login
    client.post(
        '/api/register',
        json={
            'college_id': 'LA3',
            'name': 'Lab Assist Three',
            'email': 'la3@u.edu',
            'password': 'Pass1!234',
            'role': 'lab_assistant',
        },
    )
    login_r = client.post(
        '/api/login',
        json={'college_id': 'LA3', 'password': 'Pass1!234'},
    )
    token = login_r.get_json()['token']

    # Assign lab
    cur = conn.cursor()
    created_at = datetime.datetime.now(timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO lab_assistant_assignments"
        " (lab_id, assistant_college_id, assigned_at)"
        " VALUES (?, ?, ?)",
        (lab_id, 'LA3', created_at),
    )
    conn.commit()

    # Fetch without date parameter (should default to today)
    r = client.get(
        '/api/lab-assistant/labs/assigned',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data['date'] == date_str
    assert len(data['assigned_labs']) == 1

def test_lab_assistant_endpoint_requires_role(client):
    """Only lab assistants should access the lab assistant endpoint."""
    # Register and login as student
    client.post(
        '/api/register',
        json={
            'college_id': 'S3',
            'name': 'Student Three',
            'email': 's3@u.edu',
            'password': 'Pass1!234',
            'role': 'student',
        },
    )
    login_r = client.post(
        '/api/login',
        json={'college_id': 'S3', 'password': 'Pass1!234'},
    )
    token = login_r.get_json()['token']

    # Try to access lab assistant endpoint
    date_str = datetime.date.today().strftime('%Y-%m-%d')
    r = client.get(
        f'/api/lab-assistant/labs/assigned?date={date_str}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert r.status_code == 403

def test_student_cannot_see_booked_slots(client):
    """Students should not see booked slots (privacy)."""
    conn = app_module.get_db_connection()

    # Create another student to book a slot
    _create_user(conn, 'S5', 'Student Five', 's5@u.edu', 'student')

    # Create a lab with availability
    date_str = (datetime.date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date_str)
    lab_id = _create_lab(conn, 'Physics Lab', 20, '[]')
    _create_availability(conn, lab_id, day, '09:00', '17:00')

    # Create bookings for some slots
    _create_booking(conn, 'S5', 'Physics Lab', date_str, '10:00', '12:00', 'approved')

    # Register and login as student S4
    client.post(
        '/api/register',
        json={
            'college_id': 'S4',
            'name': 'Student Four',
            'email': 's4@u.edu',
            'password': 'Pass1!234',
            'role': 'student',
        },
    )
    login_r = client.post(
        '/api/login',
        json={'college_id': 'S4', 'password': 'Pass1!234'},
    )
    token = login_r.get_json()['token']

    # Fetch available labs
    r = client.get(
        f'/api/labs/available?date={date_str}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert r.status_code == 200
    data = r.get_json()
    # Check that the response does not include booking details
    # (bookings are only shown to admins and lab assistants)
    if data['labs']:
        lab = data['labs'][0]
        # Students should not have 'bookings' key in their response
        assert 'bookings' not in lab or not lab.get('bookings')

def test_admin_sees_all_labs_including_disabled(client):
    """Admins should see all labs, even disabled ones."""
    conn = app_module.get_db_connection()

    # Create labs
    date_str = (datetime.date.today() + timedelta(days=2)).strftime('%Y-%m-%d')
    day = app_module.get_day_of_week(date_str)
    lab1_id = _create_lab(conn, 'Lab A', 15, '[]')
    lab2_id = _create_lab(conn, 'Lab B', 20, '[]')
    _create_availability(conn, lab1_id, day, '09:00', '11:00')
    _create_availability(conn, lab2_id, day, '09:00', '11:00')

    # Register and login as admin
    client.post(
        '/api/register',
        json={
            'college_id': 'A1',
            'name': 'Admin One',
            'email': 'a1@u.edu',
            'password': 'Pass1!234',
            'role': 'admin',
        },
    )
    login_r = client.post(
        '/api/login',
        json={'college_id': 'A1', 'password': 'Pass1!234'},
    )
    token = login_r.get_json()['token']

    # Disable lab1
    cur = conn.cursor()
    created_at = datetime.datetime.now(timezone.utc).isoformat()
    cur.execute(
        "INSERT INTO disabled_labs (lab_id, disabled_date, reason, created_at)"
        " VALUES (?, ?, ?, ?)",
        (lab1_id, date_str, 'Maintenance', created_at),
    )
    conn.commit()

    # Admin should see both labs (including disabled one)
    r = client.get(
        f'/api/admin/labs/available?date={date_str}',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert len(data['labs']) == 2
    disabled_lab = next(
        (lab for lab in data['labs'] if lab['lab_name'] == 'Lab A'),
        None
    )
    assert disabled_lab
    assert disabled_lab['disabled'] is True
