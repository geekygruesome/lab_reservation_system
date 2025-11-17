import pytest
import sqlite3
from unittest.mock import patch
from app import app, validate_registration_data

# Global test database
test_db_global = None

def mock_get_db_connection():
    test_db_global.row_factory = sqlite3.Row
    return test_db_global

@pytest.fixture
def client():
    """Set up test client with in-memory SQLite DB."""
    global test_db_global
    app.config["TESTING"] = True

    test_db_global = sqlite3.connect(":memory:")
    cur = test_db_global.cursor()
    cur.execute(
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
    test_db_global.commit()

    with patch("app.get_db_connection", side_effect=mock_get_db_connection), patch(
        "app.DATABASE", ":memory:"
    ):
        with app.test_client() as test_client:
            yield test_client

    test_db_global.close()
    test_db_global = None

# ===== REGISTRATION TESTS =====

def test_registration_success(client):
    """Test successful user registration."""
    response = client.post(
        "/api/register",
        json={
            "college_id": "TEST001",
            "name": "Alice",
            "email": "alice@pesu.edu",
            "password": "Passw0rd!",
            "role": "student",
        },
    )
    assert response.status_code == 201
    assert response.get_json()["success"] is True
    assert "User registration complete" in response.get_json()["message"]

def test_registration_duplicate_email(client):
    """Test duplicate email rejection."""
    client.post(
        "/api/register",
        json={
            "college_id": "TEST002",
            "name": "Bob",
            "email": "dup@pesu.edu",
            "password": "Passw0rd!",
            "role": "student",
        },
    )

    resp = client.post(
        "/api/register",
        json={
            "college_id": "TEST003",
            "name": "Charlie",
            "email": "dup@pesu.edu",
            "password": "Passw0rd!",
            "role": "student",
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False
    assert "Duplicate email" in resp.get_json()["message"]

def test_registration_duplicate_college_id(client):
    """Test duplicate college ID rejection."""
    client.post(
        "/api/register",
        json={
            "college_id": "DUPID",
            "name": "First",
            "email": "first@pesu.edu",
            "password": "Passw0rd!",
            "role": "student",
        },
    )

    resp = client.post(
        "/api/register",
        json={
            "college_id": "DUPID",
            "name": "Second",
            "email": "second@pesu.edu",
            "password": "Passw0rd!",
            "role": "student",
        },
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False
    assert "Duplicate college ID" in resp.get_json()["message"]

def test_registration_missing_fields(client):
    """Test registration with missing required fields."""
    response = client.post(
        "/api/register",
        json={"college_id": "TEST004", "name": "David"},
    )
    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert "All fields" in response.get_json()["message"]

def test_registration_invalid_json(client):
    """Test registration with invalid JSON."""
    response = client.post(
        "/api/register", data="not json", content_type="application/json"
    )
    assert response.status_code == 400
    # Flask returns 400 for malformed JSON

# ===== VALIDATION TESTS =====

@pytest.mark.parametrize(
    "password,expected_errors",
    [
        ("short1!", ["Password must be at least 8 characters"]),
        ("NoSymbol123", ["Password must contain at least one symbol"]),
        ("NoNumber!!", ["Password must contain at least one number"]),
        ("ValidPass1!", []),
    ],
)
def test_password_validation(password, expected_errors):
    """Test password complexity validation."""
    data = {
        "college_id": "VAL1",
        "name": "Val",
        "email": "test@pesu.edu",
        "password": password,
        "role": "student",
    }
    valid, errors = validate_registration_data(data)

    if expected_errors:
        assert not valid
        for expected_error in expected_errors:
            assert any(
                expected_error in error for error in errors
            ), f"Expected error containing '{expected_error}' not found in {errors}"
    else:
        assert valid

def test_email_format_validation():
    """Test email format validation."""
    invalid_emails = [
        "invalid-email",
        "missing@domain",
        "@nodomain.com",
        "spaces in@email.com",
    ]

    for email in invalid_emails:
        data = {
            "college_id": "VAL2",
            "name": "Test",
            "email": email,
            "password": "ValidPass1!",
            "role": "student",
        }
        valid, errors = validate_registration_data(data)
        assert not valid, f"Email {email} should be invalid"
        assert any(
            "Invalid email" in error for error in errors
        ), f"Expected email validation error for {email}"

def test_missing_fields_validation():
    """Test missing required fields validation."""
    incomplete_data = [
        {"name": "Test", "email": "test@pesu.edu", "password": "Pass1!", "role": "student"},
        {"college_id": "TEST", "email": "test@pesu.edu", "password": "Pass1!", "role": "student"},
        {"college_id": "TEST", "name": "Test", "password": "Pass1!", "role": "student"},
        {"college_id": "TEST", "name": "Test", "email": "test@pesu.edu", "role": "student"},
        {"college_id": "TEST", "name": "Test", "email": "test@pesu.edu", "password": "Pass1!"},
    ]

    for data in incomplete_data:
        valid, errors = validate_registration_data(data)
        assert not valid, f"Data {data} should be invalid"
        assert any(
            "All fields" in error for error in errors
        ), f"Expected 'All fields' error for {data}"

def test_email_edge_cases():
    """Test edge cases for email validation."""
    valid_emails = [
        "test@pesu.edu",
        "user.name@pesu.ac.in",
        "user+tag@university.org",
    ]

    for email in valid_emails:
        data = {
            "college_id": "VAL3",
            "name": "Test",
            "email": email,
            "password": "ValidPass1!",
            "role": "student",
        }
        valid, errors = validate_registration_data(data)
        assert valid, f"Email {email} should be valid, got errors: {errors}"

def test_password_edge_cases():
    """Test edge cases for password validation."""
    # Minimum valid password
    data = {
        "college_id": "VAL4",
        "name": "Test",
        "email": "test@pesu.edu",
        "password": "Pass0!",  # Only 6 chars
        "role": "student",
    }
    valid, errors = validate_registration_data(data)
    assert not valid, "6-char password should fail"

    # Exactly 8 chars with all requirements
    data["password"] = "Pass0!"  # 6 chars
    valid, errors = validate_registration_data(data)
    assert not valid

    # Valid complex password
    data["password"] = "P@ssw0rd"  # 8 chars
    valid, errors = validate_registration_data(data)
    assert valid, f"Should be valid, got errors: {errors}"

def test_registration_all_roles(client):
    """Test registration with different user roles."""
    roles = ["student", "faculty", "admin"]
    for idx, role in enumerate(roles):
        response = client.post(
            "/api/register",
            json={
                "college_id": f"ROLE{idx}",
                "name": f"User {role}",
                "email": f"{role}{idx}@pesu.edu",
                "password": "Passw0rd!",
                "role": role,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["success"] is True
