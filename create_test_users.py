"""
Script to create test users for manual testing.
Run this script to create users mentioned in MANUAL_TESTING_GUIDE.md
"""
import sqlite3
from werkzeug.security import generate_password_hash

# Test users from MANUAL_TESTING_GUIDE.md
test_users = [
    {
        "college_id": "STU001",
        "name": "Test Student",
        "email": "student@test.com",
        "role": "student",
        "password": "Test123!@#"
    },
    {
        "college_id": "ADM001",
        "name": "Test Admin",
        "email": "admin@test.com",
        "role": "admin",
        "password": "Admin123!@#"
    },
    {
        "college_id": "LAB001",
        "name": "Test Lab Assistant",
        "email": "lab@test.com",
        "role": "lab_assistant",
        "password": "Lab123!@#"
    },
    {
        "college_id": "FAC001",
        "name": "Test Faculty",
        "email": "faculty@test.com",
        "role": "faculty",
        "password": "Fac123!@#"
    }
]

def create_test_users():
    conn = sqlite3.connect("lab_reservations.db")
    cursor = conn.cursor()
    
    # Ensure users table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            college_id TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );
    """)
    
    created = 0
    skipped = 0
    
    for user in test_users:
        try:
            password_hash = generate_password_hash(user["password"])
            cursor.execute("""
                INSERT INTO users (college_id, name, email, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
            """, (
                user["college_id"],
                user["name"],
                user["email"],
                password_hash,
                user["role"]
            ))
            created += 1
            print(f"[OK] Created user: {user['college_id']} ({user['role']})")
        except sqlite3.IntegrityError:
            skipped += 1
            print(f"[SKIP] User {user['college_id']} already exists, skipping...")
    
    conn.commit()
    conn.close()
    
    print(f"\n[SUMMARY] {created} users created, {skipped} skipped")
    print("\n[TEST CREDENTIALS]")
    print("=" * 50)
    for user in test_users:
        print(f"College ID: {user['college_id']}")
        print(f"Password: {user['password']}")
        print(f"Role: {user['role']}")
        print("-" * 50)

if __name__ == "__main__":
    print("Creating test users from MANUAL_TESTING_GUIDE.md...")
    print("=" * 50)
    create_test_users()
    print("\n[DONE] You can now login with any of these credentials.")

