#!/usr/bin/env python3
"""
Script to add sample labs with their time slots to the database.
This creates ready-to-use labs for testing and demonstration.
"""

import sqlite3
import datetime
from datetime import timezone

# Sample labs to create
SAMPLE_LABS = [
    {
        "name": "Computer Lab A",
        "capacity": 30,
        "equipment": ["Computer", "Projector", "Whiteboard", "Printer"]
    },
    {
        "name": "Computer Lab B",
        "capacity": 25,
        "equipment": ["Computer", "Projector", "Scanner"]
    },
    {
        "name": "Electronics Lab",
        "capacity": 20,
        "equipment": ["Oscilloscope", "Multimeter", "Breadboard", "Power Supply"]
    },
    {
        "name": "Networking Lab",
        "capacity": 15,
        "equipment": ["Router", "Switch", "Cable Tester", "Network Analyzer"]
    },
    {
        "name": "Software Development Lab",
        "capacity": 35,
        "equipment": ["Computer", "Dual Monitor", "Development Tools"]
    }
]

# Time slots for each weekday
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TIME_SLOTS = [
    ("09:00", "11:00"),  # Morning slot 1
    ("11:00", "13:00"),  # Morning slot 2
    ("14:00", "16:00"),  # Afternoon slot 1
    ("16:00", "18:00"),  # Afternoon slot 2
]


def create_sample_labs():
    """Create sample labs with their time slots."""
    conn = sqlite3.connect("lab_reservations.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Ensure tables exist
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
    
    conn.commit()
    
    labs_created = 0
    labs_skipped = 0
    slots_created = 0
    
    for lab_data in SAMPLE_LABS:
        try:
            # Check if lab already exists
            cursor.execute("SELECT id FROM labs WHERE name = ?", (lab_data["name"],))
            existing = cursor.fetchone()
            
            if existing:
                print(f"[SKIP] Lab '{lab_data['name']}' already exists. Skipping...")
                labs_skipped += 1
                lab_id = existing["id"]
            else:
                # Create lab
                import json
                equipment_json = json.dumps(lab_data["equipment"])
                created_at = datetime.datetime.now(timezone.utc).isoformat()
                
                cursor.execute(
                    """INSERT INTO labs (name, capacity, equipment, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (lab_data["name"], lab_data["capacity"], equipment_json, created_at)
                )
                conn.commit()
                lab_id = cursor.lastrowid
                labs_created += 1
                print(f"[OK] Created lab: {lab_data['name']} (Capacity: {lab_data['capacity']})")
            
            # Add time slots for this lab
            slots_added = 0
            for day_of_week in WEEKDAYS:
                for start_time, end_time in TIME_SLOTS:
                    # Check if slot already exists
                    cursor.execute(
                        """SELECT id FROM availability_slots 
                           WHERE lab_id = ? AND day_of_week = ? 
                           AND start_time = ? AND end_time = ?""",
                        (lab_id, day_of_week, start_time, end_time)
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            """INSERT INTO availability_slots 
                               (lab_id, day_of_week, start_time, end_time)
                               VALUES (?, ?, ?, ?)""",
                            (lab_id, day_of_week, start_time, end_time)
                        )
                        slots_added += 1
                        slots_created += 1
            
            if slots_added > 0:
                print(f"   Added {slots_added} time slots for {lab_data['name']}")
            else:
                print(f"   Time slots already exist for {lab_data['name']}")
                
        except sqlite3.IntegrityError as e:
            print(f"[ERROR] Error creating lab '{lab_data['name']}': {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error for '{lab_data['name']}': {e}")
    
    conn.commit()
    conn.close()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"[OK] Labs created: {labs_created}")
    print(f"[SKIP] Labs skipped (already exist): {labs_skipped}")
    print(f"[OK] Time slots added: {slots_created}")
    print(f"\nTime slots configured:")
    print(f"   - Weekdays: {', '.join(WEEKDAYS)}")
    print(f"   - Slots per day: {len(TIME_SLOTS)}")
    print(f"   - Total slots per lab: {len(WEEKDAYS) * len(TIME_SLOTS)}")
    print("\n[SUCCESS] Sample labs are ready to use!")
    print("   You can now view them in the 'Available Labs' section.")


if __name__ == "__main__":
    print("Starting sample labs creation...")
    print("="*60)
    create_sample_labs()

