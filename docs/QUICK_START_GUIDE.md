# Quick Start Guide - Lab Management System

## For Admin Users

### Step 1: Login as Admin
- Use admin credentials (e.g., College ID: `ADM001`, Password: `Admin123!@#`)

### Step 2: Create Your First Lab
1. **Click on "Manage Labs" card** in the dashboard
2. **Click "+ Add New Lab" button**
3. **Fill in the form:**
   - **Lab Name:** e.g., "Computer Lab A"
   - **Capacity:** e.g., 30 (number of students)
   - **Equipment:** Enter as JSON array or comma-separated:
     - JSON format: `["Computer", "Projector", "Whiteboard"]`
     - OR comma-separated: `Computer, Projector, Whiteboard`
4. **Click "Save Lab"**
5. The lab will appear in the table immediately!

### Step 3: Create More Labs (Optional)
- Repeat Step 2 to create additional labs

### Step 4: Test Lab Management
- **Edit a Lab:** Click "Edit" button → Modify details → Click "Save Lab"
- **Delete a Lab:** Click "Delete" button → Confirm → Lab and all its availability slots are deleted

### Step 5: Test Reservations
- **Click "Reserve Lab" card**
- Select a lab from the dropdown
- Choose date and times
- Click "Create Booking"

---

## Troubleshooting

### "No labs available" Message
**If you're an admin:**
- The system will ask if you want to create a lab
- Click "OK" to go directly to Lab Management
- Or manually click "Manage Labs" card

**If you're not an admin:**
- Contact an admin to create labs first

### "Manage Labs" Card Not Visible
- Make sure you're logged in as an admin
- Check that your role is "admin" in the database
- Refresh the page

### Can't Create Lab
- Check browser console for errors (F12)
- Verify backend is running on `http://localhost:5000`
- Check that you have admin role

---

## API Endpoints (For Reference)

- `POST /api/labs` - Create lab (Admin only)
- `GET /api/labs` - Get all labs (Authenticated)
- `GET /api/labs/<id>` - Get single lab (Authenticated)
- `PUT /api/labs/<id>` - Update lab (Admin only)
- `DELETE /api/labs/<id>` - Delete lab (Admin only)

---

## Example Lab Data

**Lab Name:** Computer Lab A
**Capacity:** 30
**Equipment:** `["Desktop Computers", "Projector", "Whiteboard", "Network Switch"]`

**Lab Name:** Electronics Lab
**Capacity:** 20
**Equipment:** `["Oscilloscope", "Multimeter", "Breadboards", "Power Supply"]`

---

**Status:** ✅ System is fully functional and ready to use!

