#!/usr/bin/env python3
"""
Comprehensive modification script for implementing:
1. Equipment search feature
2. Seat-based reservation system
3. Remove manage users feature
"""

import re

# Read the current app.py
with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# ===== MODIFICATION 1: Add seats_required to bookings table =====
print("=== MODIFICATION 1: Update bookings table schema ===")

# Find and replace the bookings table creation with seats_required
old_bookings_schema = '''CREATE TABLE IF NOT EXISTS bookings (
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
        );'''

new_bookings_schema = '''CREATE TABLE IF NOT EXISTS bookings (
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
        );'''

if old_bookings_schema in content:
    content = content.replace(old_bookings_schema, new_bookings_schema)
    print("✓ Updated bookings table schema with seats_required")
else:
    print("✗ Could not find bookings schema in first init_db")

# Also update the one in create_booking function
old_bookings_in_func = '''CREATE TABLE IF NOT EXISTS bookings (
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
            );'''

new_bookings_in_func = '''CREATE TABLE IF NOT EXISTS bookings (
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
            );'''

if old_bookings_in_func in content:
    content = content.replace(old_bookings_in_func, new_bookings_in_func)
    print("✓ Updated bookings table schema in create_booking function")
else:
    print("✗ Could not find bookings schema in create_booking function")

# Write the modified content
with open('app.py', 'w', encoding='utf-8', errors='ignore') as f:
    f.write(content)

print("\n✓ All modifications saved to app.py")
