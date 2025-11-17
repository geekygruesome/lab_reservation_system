"""
Comprehensive tests for new features:
1. Equipment search (student/faculty only)
2. Seat-based reservation system
3. Manage users removal verification
"""

import sqlite3
import pytest
import json
import datetime
from datetime import timezone, timedelta
from werkzeug.security import generate_password_hash
import jwt
import app as app_module

@pytest.fixture
def client(monkeypatch):
    """Set up test database with all required tables including seats_required"""
    app_module.app.config["TESTING"] = True
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            college_id TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );
    """)

    # Create bookings table with seats_required
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            college_id TEXT NOT NULL,
            lab_name TEXT NOT NULL,
            booking_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            seats_required INTEGER DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (college_id) REFERENCES users(college_id)
        );
    """)

    # Create labs table
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

    # Create availability_slots table
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

    # Create disabled_labs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disabled_labs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            disabled_date TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE CASCADE
        );
    """)

    # Create equipment_availability table
    cursor.execute("""
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
    """)

    # Create lab_assistant_assignments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lab_assistant_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            assistant_college_id TEXT NOT NULL,
            assigned_at TEXT NOT NULL,
            FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE CASCADE,
            FOREIGN KEY (assistant_college_id) REFERENCES users(college_id)
        );
    """)

    conn.commit()

    # Register test users
    today = datetime.datetime.now(timezone.utc).isoformat()
    cursor.execute(
        "INSERT INTO users (college_id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        ("STU001", "John Student", "student@example.com", generate_password_hash("password123!"), "student"),
    )
    cursor.execute(
        "INSERT INTO users (college_id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        ("FAC001", "Jane Faculty", "faculty@example.com", generate_password_hash("password123!"), "faculty"),
    )
    cursor.execute(
        "INSERT INTO users (college_id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        ("ADM001", "Admin User", "admin@example.com", generate_password_hash("password123!"), "admin"),
    )
    cursor.execute(
        "INSERT INTO users (college_id, name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
        ("LAB001", "Lab Assistant", "lab@example.com", generate_password_hash("password123!"), "lab_assistant"),
    )

    # Insert test labs with equipment
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Electronics Lab", 20, "Arduino, Oscilloscope, Power Supply", today),
    )
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Biology Lab", 15, "Microscope, Burner, Slides", today),
    )
    cursor.execute(
        "INSERT INTO labs (name, capacity, equipment, created_at) VALUES (?, ?, ?, ?)",
        ("Chemistry Lab", 25, "Burner, Beakers, Test Tubes", today),
    )

    conn.commit()

    # Patch get_db_connection to return test connection and set DATABASE to :memory:
    monkeypatch.setattr(app_module, "get_db_connection", lambda: conn)
    monkeypatch.setattr(app_module, "DATABASE", ":memory:")

    with app_module.app.test_client() as test_client:
        yield test_client

    conn.close()

def get_token(role, college_id, name):
    """Helper to generate JWT token"""
    payload = {"college_id": college_id, "role": role, "name": name}
    token = jwt.encode(payload, app_module.SECRET_KEY, algorithm="HS256")
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token

class TestEquipmentSearch:
    """Test equipment search feature"""

    def test_equipment_search_by_student(self, client):
        """Student should be able to search by equipment"""
        token = get_token("student", "STU001", "John Student")
        response = client.get(
            "/api/labs/search/equipment?equipment=Arduino",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert len(data["labs"]) == 1
        assert data["labs"][0]["name"] == "Electronics Lab"
        assert "Arduino" in data["labs"][0]["equipment"]

    def test_equipment_search_by_faculty(self, client):
        """Faculty should be able to search by equipment"""
        token = get_token("faculty", "FAC001", "Jane Faculty")
        response = client.get(
            "/api/labs/search/equipment?equipment=Microscope",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert len(data["labs"]) == 1
        assert data["labs"][0]["name"] == "Biology Lab"

    def test_equipment_search_case_insensitive(self, client):
        """Equipment search should be case-insensitive"""
        token = get_token("student", "STU001", "John Student")
        response = client.get(
            "/api/labs/search/equipment?equipment=ARDUINO",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert len(data["labs"]) == 1

    def test_equipment_search_multiple_results(self, client):
        """Equipment search should return multiple labs with matching equipment"""
        token = get_token("student", "STU001", "John Student")
        response = client.get(
            "/api/labs/search/equipment?equipment=Burner",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert len(data["labs"]) == 2  # Biology Lab and Chemistry Lab

    def test_equipment_search_no_results(self, client):
        """Equipment search with no matches should return empty list"""
        token = get_token("student", "STU001", "John Student")
        response = client.get(
            "/api/labs/search/equipment?equipment=NonexistentEquipment",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert len(data["labs"]) == 0
        assert "No matching labs found" in data["message"]

    def test_equipment_search_requires_keyword(self, client):
        """Equipment search should require a keyword"""
        token = get_token("student", "STU001", "John Student")
        response = client.get(
            "/api/labs/search/equipment?equipment=",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_equipment_search_admin_denied(self, client):
        """Admin should NOT be able to access equipment search"""
        token = get_token("admin", "ADM001", "Admin User")
        response = client.get(
            "/api/labs/search/equipment?equipment=Arduino",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403  # Forbidden

    def test_equipment_search_lab_assistant_denied(self, client):
        """Lab assistant should NOT be able to access equipment search"""
        token = get_token("lab_assistant", "LAB001", "Lab Assistant")
        response = client.get(
            "/api/labs/search/equipment?equipment=Arduino",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403  # Forbidden

    def test_equipment_search_requires_auth(self, client):
        """Equipment search should require authentication"""
        response = client.get("/api/labs/search/equipment?equipment=Arduino")
        assert response.status_code == 401

class TestSeatsReservation:
    """Test seat-based reservation system"""

    def test_create_booking_with_seats(self, client):
        """Should create booking with seats_required field"""
        token = get_token("student", "STU001", "John Student")
        tomorrow = (datetime.datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        response = client.post(
            "/api/bookings",
            json={
                "lab_name": "Electronics Lab",
                "booking_date": tomorrow,
                "start_time": "10:00",
                "end_time": "12:00",
                "seats_required": 5,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["success"] is True
        assert "booking_id" in data

    def test_booking_seats_required_field(self, client):
        """seats_required should be a required field"""
        token = get_token("student", "STU001", "John Student")
        tomorrow = (datetime.datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        response = client.post(
            "/api/bookings",
            json={
                "lab_name": "Electronics Lab",
                "booking_date": tomorrow,
                "start_time": "10:00",
                "end_time": "12:00",
                # Missing seats_required
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Missing required fields" in data["message"]

    def test_booking_seats_must_be_positive(self, client):
        """seats_required must be at least 1"""
        token = get_token("student", "STU001", "John Student")
        tomorrow = (datetime.datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        response = client.post(
            "/api/bookings",
            json={
                "lab_name": "Electronics Lab",
                "booking_date": tomorrow,
                "start_time": "10:00",
                "end_time": "12:00",
                "seats_required": 0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "at least 1" in data["message"]

    def test_booking_seats_cannot_exceed_capacity(self, client):
        """seats_required cannot exceed lab capacity"""
        token = get_token("student", "STU001", "John Student")
        tomorrow = (datetime.datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        response = client.post(
            "/api/bookings",
            json={
                "lab_name": "Electronics Lab",  # Capacity: 20
                "booking_date": tomorrow,
                "start_time": "10:00",
                "end_time": "12:00",
                "seats_required": 25,  # Exceeds capacity
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "exceed lab capacity" in data["message"]

    def test_booking_seats_validation_non_integer(self, client):
        """seats_required must be an integer"""
        token = get_token("student", "STU001", "John Student")
        tomorrow = (datetime.datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        response = client.post(
            "/api/bookings",
            json={
                "lab_name": "Electronics Lab",
                "booking_date": tomorrow,
                "start_time": "10:00",
                "end_time": "12:00",
                "seats_required": "five",  # Not an integer
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "valid integer" in data["message"]

    def test_booking_available_seats_check(self, client):
        """Should check available seats in time slot"""
        token = get_token("student", "STU001", "John Student")
        tomorrow = (datetime.datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Create first booking with 15 seats directly via database connection
        conn = app_module.get_db_connection()
        cursor = conn.cursor()
        created_at = datetime.datetime.now(timezone.utc).isoformat()

        # Insert first booking with 15 seats (Electronics Lab capacity is 20)
        cursor.execute(
            "INSERT INTO bookings (college_id, lab_name, booking_date, start_time, end_time, seats_required, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("ADM001", "Electronics Lab", tomorrow, "10:00", "12:00", 15, "approved", created_at),
        )
        conn.commit()

        # Now try to book remaining 5 seats (should succeed - 15 + 5 = 20)
        response = client.post(
            "/api/bookings",
            json={
                "lab_name": "Electronics Lab",
                "booking_date": tomorrow,
                "start_time": "10:00",
                "end_time": "12:00",
                "seats_required": 5,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201, f"First request failed: {response.get_json()}"
        booking_id = response.get_json()["booking_id"]

        # Approve the second booking
        cursor.execute(
            "UPDATE bookings SET status = 'approved' WHERE id = ?",
            (booking_id,),
        )
        conn.commit()

        # Try to book 1 more seat (should fail - no seats available, 20 total occupied)
        response = client.post(
            "/api/bookings",
            json={
                "lab_name": "Electronics Lab",
                "booking_date": tomorrow,
                "start_time": "10:00",
                "end_time": "12:00",
                "seats_required": 1,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.get_json()}"
        data = response.get_json()
        assert "Not enough available seats" in data["message"]

class TestManageUsersRemoval:
    """Test that Manage Users feature is removed"""

    def test_manage_users_not_in_dashboard(self, client):
        """Manage Users should not appear in dashboard.html"""
        response = client.get("/dashboard.html")
        assert response.status_code == 200
        content = response.data.decode('utf-8')
        # Should not have "Manage Users" card
        assert "Manage Users" not in content

    def test_no_manage_users_route(self, client):
        """Should not have a manage users route"""
        token = get_token("admin", "ADM001", "Admin User")
        # Try common manage users routes
        for route in ["/api/admin/users", "/api/users/manage", "/manage-users", "/api/manage/users"]:
            response = client.get(route, headers={"Authorization": f"Bearer {token}"})
            # Either 404 or not found, but not accessible
            assert response.status_code in [404, 405, 401]  # Not Found, Method Not Allowed, or Unauthorized

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
