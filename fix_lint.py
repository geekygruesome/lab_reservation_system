#!/usr/bin/env python3
"""Fix linting issues in app.py"""

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix long lines around seat checking (lines 619, 623)
# These are SQL queries that are too long

# Replace line 619 (the SELECT SUM query)
for i in range(len(lines)):
    if i == 618 and 'SELECT SUM' in lines[i]:  # 0-indexed so line 619 is index 618
        # Split this query into multiple lines
        lines[i] = ('                cursor.execute(\n'
                   '                    "SELECT SUM(COALESCE(seats_required, 1)) as total_seats "\n'
                   '                    "FROM bookings WHERE lab_name = ? AND booking_date = ? "\n'
                   '                    "AND status = \'approved\' AND NOT (end_time <= ? OR start_time >= ?)",\n')
        break

# Write back
with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fixed long line issues")
