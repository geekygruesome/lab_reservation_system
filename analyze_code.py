#!/usr/bin/env python3
import re

with open('app.py', 'r') as f:
    content = f.read()
    lines = content.split('\n')

# Find all routes
print("=== ROUTES IN APP.PY ===")
routes = re.findall(r'@app\.route\(["\']([^"\']+)["\'][^)]*\)', content)
for route in sorted(set(routes)):
    print(f"  - {route}")

# Look for manage-users
print("\n=== MANAGE USERS REFERENCES ===")
for i, line in enumerate(lines):
    if 'manage' in line.lower() and 'user' in line.lower():
        print(f"Line {i+1}: {line.strip()}")

# Look for booking routes
print("\n=== BOOKING RELATED ROUTES ===")
for i, line in enumerate(lines):
    if '@app.route' in line:
        if any(word in lines[i+1].lower() if i+1 < len(lines) else False for word in ['booking', 'reserve', 'seat']):
            print(f"Line {i+1}: {line.strip()}")
            if i+1 < len(lines):
                print(f"Line {i+2}: {lines[i+1].strip()}")

# Search for "seats" or similar
print("\n=== SEAT-RELATED REFERENCES ===")
for i, line in enumerate(lines):
    if 'seat' in line.lower():
        print(f"Line {i+1}: {line.strip()[:100]}")
