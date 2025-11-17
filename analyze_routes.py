#!/usr/bin/env python3
import re
import json

with open('app.py', 'r') as f:
    lines = f.readlines()

# Find bookings route
print("=" * 80)
print("SEARCHING FOR /api/bookings POST ROUTE")
print("=" * 80)
for i, line in enumerate(lines):
    if '@app.route' in line and '/api/bookings' in line:
        if i + 1 < len(lines) and 'methods' in line and 'POST' in line:
            print(f"\nFound at line {i+1}")
            for j in range(i, min(i + 100, len(lines))):
                print(f'{j+1:4d}: {lines[j]}', end='')
            break
        elif i + 1 < len(lines) and 'POST' in lines[i+1]:
            print(f"\nFound at line {i+1}")
            for j in range(i, min(i + 100, len(lines))):
                print(f'{j+1:4d}: {lines[j]}', end='')
            break

# Find available labs route
print("\n" + "=" * 80)
print("SEARCHING FOR /api/labs/available ROUTE")
print("=" * 80)
for i, line in enumerate(lines):
    if '@app.route' in line and '/api/labs/available' in line:
        print(f"\nFound at line {i+1}")
        for j in range(i, min(i + 80, len(lines))):
            print(f'{j+1:4d}: {lines[j]}', end='')
        break
