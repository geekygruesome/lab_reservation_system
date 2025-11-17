#!/usr/bin/env python3
"""Check database status and equipment_availability table."""

import sqlite3
import os

DATABASE = "lab_reservations.db"

print("=" * 60)
print("DATABASE CHECK")
print("=" * 60)

# Check if database exists
if os.path.exists(DATABASE):
    print(f"\n[OK] Database file exists: {DATABASE}")
    print(f"  File size: {os.path.getsize(DATABASE)} bytes")
else:
    print(f"\n[ERROR] Database file does NOT exist: {DATABASE}")
    print("  It will be created when you start the Flask server.")
    exit(0)

# Connect and check tables
try:
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check if equipment_availability table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='equipment_availability'
    """)
    table_exists = cursor.fetchone() is not None
    
    if table_exists:
        print("\n[OK] equipment_availability table EXISTS")
        
        # Count entries
        cursor.execute("SELECT COUNT(*) FROM equipment_availability")
        count = cursor.fetchone()[0]
        print(f"  Total equipment availability entries: {count}")
        
        # Show sample entries
        cursor.execute("""
            SELECT lab_id, equipment_name, is_available 
            FROM equipment_availability 
            LIMIT 5
        """)
        entries = cursor.fetchall()
        if entries:
            print("\n  Sample entries:")
            for entry in entries:
                print(f"    Lab {entry[0]}: {entry[1]} = {entry[2]}")
    else:
        print("\n[ERROR] equipment_availability table does NOT exist")
        print("  The table will be created when you start the Flask server.")
    
    # Check labs
    cursor.execute("SELECT COUNT(*) FROM labs")
    lab_count = cursor.fetchone()[0]
    print(f"\n[OK] Labs in database: {lab_count}")
    
    if lab_count > 0:
        cursor.execute("SELECT id, name, equipment FROM labs LIMIT 3")
        labs = cursor.fetchall()
        print("\n  Sample labs:")
        for lab in labs:
            print(f"    Lab {lab[0]}: {lab[1]}")
            print(f"      Equipment: {lab[2]}")
    
    conn.close()
    print("\n" + "=" * 60)
    print("STATUS: Database looks good!")
    print("=" * 60)
    
except sqlite3.Error as e:
    print(f"\n[ERROR] Database error: {e}")
except Exception as e:
    print(f"\n[ERROR] Error: {e}")

