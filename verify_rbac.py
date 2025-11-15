#!/usr/bin/env python3
"""
Quick RBAC Verification Script
Tests role-based access control to verify it's working correctly.
"""

import requests
import json

BASE_URL = "http://localhost:5000"

def print_test(name, passed, details=""):
    """Print test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {name}")
    if details:
        print(f"   {details}")
    print()

def register_user(college_id, name, email, password, role):
    """Register a new user."""
    response = requests.post(
        f"{BASE_URL}/api/register",
        json={
            "college_id": college_id,
            "name": name,
            "email": email,
            "password": password,
            "role": role
        }
    )
    return response.status_code == 201

def login_user(college_id, password):
    """Login and get token."""
    response = requests.post(
        f"{BASE_URL}/api/login",
        json={"college_id": college_id, "password": password}
    )
    if response.status_code == 200:
        return response.json()["token"]
    return None

def create_booking(token, lab_name="Test Lab", date="2024-12-25", start="10:00", end="12:00"):
    """Create a booking request."""
    response = requests.post(
        f"{BASE_URL}/api/bookings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "lab_name": lab_name,
            "booking_date": date,
            "start_time": start,
            "end_time": end
        }
    )
    if response.status_code == 201:
        return response.json().get("booking_id")
    return None

def main():
    print("=" * 60)
    print("RBAC VERIFICATION SCRIPT")
    print("=" * 60)
    print()
    
    # Test 1: Register users
    print("Test 1: Registering users...")
    student_reg = register_user("RBAC_STU", "RBAC Student", "rbac_stu@test.com", "Test123!@#", "student")
    admin_reg = register_user("RBAC_ADM", "RBAC Admin", "rbac_adm@test.com", "Admin123!@#", "admin")
    lab_reg = register_user("RBAC_LAB", "RBAC Lab Asst", "rbac_lab@test.com", "Lab123!@#", "lab_assistant")
    
    print_test("Student Registration", student_reg)
    print_test("Admin Registration", admin_reg)
    print_test("Lab Assistant Registration", lab_reg)
    
    if not (student_reg and admin_reg and lab_reg):
        print("❌ Registration failed. Cannot continue.")
        return
    
    # Test 2: Login and get tokens
    print("Test 2: Logging in...")
    student_token = login_user("RBAC_STU", "Test123!@#")
    admin_token = login_user("RBAC_ADM", "Admin123!@#")
    lab_token = login_user("RBAC_LAB", "Lab123!@#")
    
    print_test("Student Login", student_token is not None)
    print_test("Admin Login", admin_token is not None)
    print_test("Lab Assistant Login", lab_token is not None)
    
    if not (student_token and admin_token and lab_token):
        print("❌ Login failed. Cannot continue.")
        return
    
    # Test 3: Create booking as student
    print("Test 3: Creating booking as student...")
    booking_id = create_booking(student_token)
    print_test("Student Creates Booking", booking_id is not None, f"Booking ID: {booking_id}")
    
    if not booking_id:
        print("❌ Booking creation failed. Cannot continue.")
        return
    
    # Test 4: Student tries to access admin endpoint (should fail)
    print("Test 4: Testing role-based access restrictions...")
    response = requests.get(
        f"{BASE_URL}/api/bookings/pending",
        headers={"Authorization": f"Bearer {student_token}"}
    )
    student_blocked = response.status_code == 403
    print_test(
        "Student Blocked from Admin Endpoint",
        student_blocked,
        f"Status: {response.status_code} (Expected: 403)"
    )
    
    # Test 5: Student tries to approve booking (should fail)
    response = requests.post(
        f"{BASE_URL}/api/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {student_token}"}
    )
    student_cannot_approve = response.status_code == 403
    print_test(
        "Student Cannot Approve Booking",
        student_cannot_approve,
        f"Status: {response.status_code} (Expected: 403)"
    )
    
    # Test 6: Lab Assistant tries to access admin endpoint (should fail)
    response = requests.get(
        f"{BASE_URL}/api/bookings/pending",
        headers={"Authorization": f"Bearer {lab_token}"}
    )
    lab_blocked = response.status_code == 403
    print_test(
        "Lab Assistant Blocked from Admin Endpoint",
        lab_blocked,
        f"Status: {response.status_code} (Expected: 403)"
    )
    
    # Test 7: Admin can access admin endpoint (should succeed)
    response = requests.get(
        f"{BASE_URL}/api/bookings/pending",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    admin_access = response.status_code == 200
    pending_count = len(response.json().get("bookings", [])) if admin_access else 0
    print_test(
        "Admin Can Access Admin Endpoint",
        admin_access,
        f"Status: {response.status_code} (Expected: 200), Pending bookings: {pending_count}"
    )
    
    # Test 8: Admin can approve booking (should succeed)
    response = requests.post(
        f"{BASE_URL}/api/bookings/{booking_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    admin_can_approve = response.status_code == 200
    print_test(
        "Admin Can Approve Booking",
        admin_can_approve,
        f"Status: {response.status_code} (Expected: 200)"
    )
    
    # Test 9: Unauthenticated access (should fail)
    response = requests.get(f"{BASE_URL}/api/bookings")
    unauth_blocked = response.status_code == 401
    print_test(
        "Unauthenticated Access Blocked",
        unauth_blocked,
        f"Status: {response.status_code} (Expected: 401)"
    )
    
    # Test 10: Student can view own bookings
    response = requests.get(
        f"{BASE_URL}/api/bookings",
        headers={"Authorization": f"Bearer {student_token}"}
    )
    student_sees_own = response.status_code == 200
    if student_sees_own:
        bookings = response.json().get("bookings", [])
        student_booking_count = len(bookings)
    else:
        student_booking_count = 0
    print_test(
        "Student Can View Own Bookings",
        student_sees_own,
        f"Status: {response.status_code} (Expected: 200), Bookings: {student_booking_count}"
    )
    
    # Test 11: Admin can view all bookings
    response = requests.get(
        f"{BASE_URL}/api/bookings",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    admin_sees_all = response.status_code == 200
    if admin_sees_all:
        bookings = response.json().get("bookings", [])
        admin_booking_count = len(bookings)
    else:
        admin_booking_count = 0
    print_test(
        "Admin Can View All Bookings",
        admin_sees_all,
        f"Status: {response.status_code} (Expected: 200), Bookings: {admin_booking_count}"
    )
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_tests = [
        ("Student Registration", student_reg),
        ("Admin Registration", admin_reg),
        ("Lab Assistant Registration", lab_reg),
        ("Student Login", student_token is not None),
        ("Admin Login", admin_token is not None),
        ("Lab Assistant Login", lab_token is not None),
        ("Student Creates Booking", booking_id is not None),
        ("Student Blocked from Admin Endpoint", student_blocked),
        ("Student Cannot Approve", student_cannot_approve),
        ("Lab Assistant Blocked", lab_blocked),
        ("Admin Can Access Admin Endpoint", admin_access),
        ("Admin Can Approve", admin_can_approve),
        ("Unauthenticated Blocked", unauth_blocked),
        ("Student Views Own Bookings", student_sees_own),
        ("Admin Views All Bookings", admin_sees_all),
    ]
    
    passed = sum(1 for _, result in all_tests if result)
    total = len(all_tests)
    
    print(f"\nTests Passed: {passed}/{total}")
    print(f"Tests Failed: {total - passed}/{total}")
    print()
    
    if passed == total:
        print("✅ ALL TESTS PASSED - RBAC IS WORKING CORRECTLY!")
    else:
        print("❌ SOME TESTS FAILED - RBAC MAY HAVE ISSUES")
        print("\nFailed tests:")
        for name, result in all_tests:
            if not result:
                print(f"  - {name}")
    
    print()
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Cannot connect to server.")
        print("   Make sure Flask server is running: python app.py")
    except Exception as e:
        print(f"❌ ERROR: {e}")

