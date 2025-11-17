#!/usr/bin/env python3
"""Remove inline 'import traceback' statements since it's now imported at top-level."""

import re

with open('app.py', 'r') as f:
    content = f.read()

# Remove lines that are just "import traceback" with optional whitespace
# This keeps the structure intact
lines = content.split('\n')
cleaned_lines = []

for line in lines:
    # Skip lines that are only "import traceback" (with whitespace)
    if re.match(r'^\s*import\s+traceback\s*$', line):
        continue
    cleaned_lines.append(line)

cleaned_content = '\n'.join(cleaned_lines)

with open('app.py', 'w') as f:
    f.write(cleaned_content)

print("✅ Removed inline 'import traceback' statements")
