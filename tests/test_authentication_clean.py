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
