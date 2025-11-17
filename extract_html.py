#!/usr/bin/env python3
import os

# Read dashboard.html with UTF-8
with open('dashboard.html', 'r', encoding='utf-8', errors='ignore') as f:
    dashboard_content = f.read()

# Read available_labs.html
with open('available_labs.html', 'r', encoding='utf-8', errors='ignore') as f:
    available_labs_content = f.read()

# Find manage users section
print("=" * 80)
print("MANAGE USERS IN DASHBOARD")
print("=" * 80)
manage_start = dashboard_content.find('Manage Users')
if manage_start > 0:
    section_start = dashboard_content.rfind('<', 0, manage_start)
    section_end = dashboard_content.find('</section>', manage_start + 100)
    if section_end > 0:
        section_end = dashboard_content.find('</section>', section_end) + len('</section>')
    section = dashboard_content[section_start:section_end if section_end > 0 else section_start + 1000]
    print(section[:1500])

# Check for admin nav
print("\n" + "=" * 80)
print("LOOKING FOR ADMIN NAVIGATION")
print("=" * 80)
if 'admin' in dashboard_content.lower():
    # Find where admin-specific sections are
    idx = dashboard_content.lower().find('admin')
    print(f"Found 'admin' at position {idx}")
    print(dashboard_content[idx-200:idx+500])

# Check available labs for equipment search UI
print("\n" + "=" * 80)
print("AVAILABLE LABS HTML")
print("=" * 80)
print(available_labs_content[:1000])
