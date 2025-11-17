#!/usr/bin/env python3
"""
Script to add lab availability slots for all weekdays (Monday-Friday).
Adds slots for Monday, Tuesday, Wednesday, Thursday, Friday (excluding Saturday and Sunday).
"""

import sqlite3

# Lab slots configuration - slots for each weekday
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TIME_SLOTS = [
    ("09:00", "11:00"),  # Morning slot 1
    ("11:00", "13:00"),  # Morning slot 2
    ("14:00", "16:00"),  # Afternoon slot 1
    ("16:00", "18:00"),  # Afternoon slot 2
]

def add_lab_slots():
    """Add lab availability slots for all weekdays (Monday-Friday) for all labs."""
    conn = sqlite3.connect("lab_reservations.db")
    cursor = conn.cursor()
    
    # Get all lab IDs
    cursor.execute("SELECT id, name FROM labs")
    labs = cursor.fetchall()
    
    if not labs:
        print("No labs found in database. Please create labs first.")
        conn.close()
        return
    
    print(f"Found {len(labs)} lab(s) in database")
    print(f"Adding slots for weekdays: {', '.join(WEEKDAYS)}")
    print(f"Time slots: {', '.join([f'{s}-{e}' for s, e in TIME_SLOTS])}")
    
    # Insert availability slots for each lab, each weekday, each time slot
    count = 0
    skipped = 0
    for lab_id, lab_name in labs:
        for day_of_week in WEEKDAYS:
            for start_time, end_time in TIME_SLOTS:
                try:
                    # Check if slot already exists to avoid duplicates
                    cursor.execute(
                        """SELECT id FROM availability_slots 
                           WHERE lab_id = ? AND day_of_week = ? 
                           AND start_time = ? AND end_time = ?""",
                        (lab_id, day_of_week, start_time, end_time)
                    )
                    if cursor.fetchone():
                        skipped += 1
                        continue
                    
                    cursor.execute(
                        """INSERT INTO availability_slots 
                           (lab_id, day_of_week, start_time, end_time)
                           VALUES (?, ?, ?, ?)""",
                        (lab_id, day_of_week, start_time, end_time)
                    )
                    count += 1
                except Exception as e:
                    print(f"  Error adding slot for {lab_name} on {day_of_week} {start_time}-{end_time}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Added {count} new availability slots")
    if skipped > 0:
        print(f"⏭️  Skipped {skipped} duplicate slots (already exist)")
    print(f"\nSlots configured:")
    print(f"  • Weekdays: {', '.join(WEEKDAYS)}")
    print(f"  • Time slots per day: {len(TIME_SLOTS)}")
    print(f"  • Total slots per lab: {len(WEEKDAYS) * len(TIME_SLOTS)}")
    print(f"  • Total slots for all labs: {count + skipped}")

if __name__ == "__main__":
    add_lab_slots()
