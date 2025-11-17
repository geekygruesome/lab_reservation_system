#!/usr/bin/env python3
"""Remove blank lines with whitespace"""

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove whitespace from blank lines
cleaned_lines = []
for line in lines:
    if line.strip() == '':
        cleaned_lines.append('\n')
    else:
        cleaned_lines.append(line)

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(cleaned_lines)

print("Removed whitespace from blank lines")
