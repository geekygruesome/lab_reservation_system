#!/usr/bin/env python3
"""Quick test script to verify equipment availability API is working."""

import requests
import json

BASE_URL = "http://localhost:5000"

# You'll need to replace this with a valid admin token
# Get it by logging in first
ADMIN_TOKEN = "YOUR_TOKEN_HERE"

def test_equipment_availability():
    """Test if equipment availability is returned in GET /api/labs."""
    headers = {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(f"{BASE_URL}/api/labs", headers=headers)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nSuccess: {data.get('success')}")
            print(f"Number of labs: {len(data.get('labs', []))}")
            
            for lab in data.get('labs', []):
                print(f"\nLab: {lab.get('name')} (ID: {lab.get('id')})")
                print(f"  Equipment: {lab.get('equipment')}")
                print(f"  Equipment Availability:")
                if lab.get('equipment_availability'):
                    for eq in lab['equipment_availability']:
                        status = "Available" if eq['is_available'] == 'yes' else "Not Available"
                        print(f"    - {eq['equipment_name']}: {status}")
                else:
                    print("    - No equipment availability data")
        else:
            print(f"Error: {response.text}")
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to server. Make sure Flask server is running on http://localhost:5000")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Equipment Availability API Test")
    print("=" * 60)
    print("\nNOTE: You need to:")
    print("1. Start your Flask server: python app.py")
    print("2. Login as admin to get a token")
    print("3. Replace ADMIN_TOKEN in this script")
    print("=" * 60)
    print()
    
    if ADMIN_TOKEN == "YOUR_TOKEN_HERE":
        print("Please update ADMIN_TOKEN in this script first!")
    else:
        test_equipment_availability()

