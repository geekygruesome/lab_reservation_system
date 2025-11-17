#!/usr/bin/env python3
"""Extract the full app.py content to a backup and understand its structure"""
import os

with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print(f"Total lines in app.py: {len(lines)}")
print("\nKey sections:")

# Find key function/route definitions
for i, line in enumerate(lines):
    if line.strip().startswith('def ') and any(kw in line for kw in ['booking', 'available', 'labs', 'equipment', 'capacity']):
        print(f"  Line {i+1}: {line.strip()[:80]}")

print("\nDatabase schema operations:")
for i, line in enumerate(lines):
    if 'CREATE TABLE' in line:
        # Print the table name
        if 'bookings' in lines[i:i+5]:
            print(f"  Line {i+1}: bookings table")
        elif 'labs' in lines[i:i+5]:
            print(f"  Line {i+1}: labs table")

# Check current bookings schema
print("\n\nBOOKINGS TABLE COLUMNS:")
for i, line in enumerate(lines):
    if 'CREATE TABLE IF NOT EXISTS bookings' in line:
        for j in range(i, min(i+20, len(lines))):
            print(f"  {lines[j].strip()}")
            if ';' in lines[j] and ')' in lines[j]:
                break
        break
