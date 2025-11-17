#!/usr/bin/env python3
"""
Test script to reproduce booking creation flow end-to-end.
"""

import requests
import json
import jwt
from datetime import datetime, timedelta

BASE_URL = "http://localhost:5000"
SECRET_KEY = "dev-secret"  # Must match app.py SECRET_KEY (default from os.getenv)

# Step 1: Create a valid JWT token
payload = {
    "college_id": "TEST001",
    "role": "student",
    "name": "Test Student"
}
token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
if isinstance(token, bytes):
    token = token.decode("utf-8")

print(f"Generated token: {token[:50]}...")

# Step 2: Get available labs to check what labs exist
print("\n--- Step 2: Get available labs ---")
headers = {"Authorization": f"Bearer {token}"}
response = requests.get(f"{BASE_URL}/api/labs", headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

labs_data = response.json()
if labs_data.get("labs"):
    lab_names = [lab["name"] for lab in labs_data["labs"]]
    print(f"Available labs: {lab_names}")
    test_lab = lab_names[0]
else:
    test_lab = "Biology"
    print(f"No labs found, will try with '{test_lab}'")

# Step 3: Attempt to create a booking
print(f"\n--- Step 3: Create booking for lab '{test_lab}' ---")
tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
booking_payload = {
    "lab_name": test_lab,
    "booking_date": tomorrow,
    "start_time": "10:00",
    "end_time": "11:00",
    "seats_required": 1
}

print(f"Booking payload: {json.dumps(booking_payload, indent=2)}")

response = requests.post(
    f"{BASE_URL}/api/bookings",
    json=booking_payload,
    headers=headers
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

if response.status_code == 201:
    print("\n✅ BOOKING CREATED SUCCESSFULLY!")
    booking_id = response.json().get("booking_id")
    print(f"Booking ID: {booking_id}")
else:
    print("\n❌ BOOKING FAILED!")
    error_msg = response.json().get("message", "Unknown error")
    print(f"Error: {error_msg}")
