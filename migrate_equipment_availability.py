#!/usr/bin/env python3
"""
Migration script to initialize equipment_availability for existing labs.
Run this once to populate equipment availability for labs created before this feature.
"""

import sqlite3
import json
import datetime
from datetime import timezone

DATABASE = "lab_reservations.db"

def migrate_equipment_availability():
    """Initialize equipment availability for all existing labs."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Ensure equipment_availability table exists
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment_availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_id INTEGER NOT NULL,
            equipment_name TEXT NOT NULL,
            is_available TEXT NOT NULL DEFAULT 'yes',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (lab_id) REFERENCES labs(id) ON DELETE CASCADE,
            UNIQUE(lab_id, equipment_name)
        );
        """
    )
    conn.commit()
    
    # Get all labs
    cursor.execute("SELECT id, equipment FROM labs")
    labs = cursor.fetchall()
    
    migrated_count = 0
    created_at = datetime.datetime.now(timezone.utc).isoformat()
    
    for lab in labs:
        lab_id = lab["id"]
        equipment_str = lab["equipment"]
        
        # Check if this lab already has equipment availability entries
        cursor.execute(
            "SELECT COUNT(*) FROM equipment_availability WHERE lab_id = ?",
            (lab_id,)
        )
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            print(f"Lab {lab_id} already has equipment availability entries. Skipping.")
            continue
        
        # Parse equipment
        equipment_list = []
        try:
            equipment_list = json.loads(equipment_str)
            if not isinstance(equipment_list, list):
                equipment_list = [equipment_str]
        except (json.JSONDecodeError, ValueError):
            # Try comma-separated
            if ',' in equipment_str:
                equipment_list = [e.strip() for e in equipment_str.split(',') if e.strip()]
            else:
                equipment_list = [equipment_str.strip()] if equipment_str.strip() else []
        
        # Create equipment availability entries
        for equipment_name in equipment_list:
            if equipment_name and equipment_name.strip():
                try:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO equipment_availability
                        (lab_id, equipment_name, is_available, created_at)
                        VALUES (?, ?, 'yes', ?)
                        """,
                        (lab_id, equipment_name.strip(), created_at),
                    )
                    migrated_count += 1
                except sqlite3.Error as e:
                    print(f"Error creating equipment availability for lab {lab_id}, equipment {equipment_name}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\nMigration complete!")
    print(f"   - Processed {len(labs)} labs")
    print(f"   - Created {migrated_count} equipment availability entries")
    print(f"\nIMPORTANT: Restart your Flask server to see the changes!")

if __name__ == "__main__":
    migrate_equipment_availability()

