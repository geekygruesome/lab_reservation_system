#!/usr/bin/env python3
import re

with open('tests/test_authentication_clean.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Find all patterns of bookings without seats_required
pattern = r'"booking_date": "[^"]*",\s*"start_time": "[^"]*",\s*"end_time": "[^"]*"(?!\s*,\s*"seats_required")'
matches = list(re.finditer(pattern, content))
print(f"Found {len(matches)} booking requests to update")

# Now replace all of them with seats_required included
# Pattern to replace
old_pattern = r'("booking_date": "[^"]*",\s*"start_time": "[^"]*",\s*"end_time": "[^"]*")(?!\s*,\s*"seats_required")'

def replacement_func(match):
    return match.group(1) + ',\n                "seats_required": 1'

new_content = re.sub(old_pattern, replacement_func, content)

with open('tests/test_authentication_clean.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Updated test file with seats_required field")
