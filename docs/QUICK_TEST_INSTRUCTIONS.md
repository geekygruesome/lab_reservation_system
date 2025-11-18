# Quick Testing Instructions

## 🚀 Quick Start - Verify Everything Works

### Step 1: Start the Server
```bash
python app.py
```
Server should start on `http://localhost:5000`

### Step 2: Run Automated RBAC Test
```bash
# Install requests if needed
pip install requests

# Run verification script
python verify_rbac.py
```

**Expected Output:**
- ✅ All tests should pass
- If you see "ALL TESTS PASSED - RBAC IS WORKING CORRECTLY!" → ✅ RBAC is working!

---

## 🎯 Manual Browser Testing (5 minutes)

### Test 1: Register & Login
1. Open `register.html` in browser
2. Register as **Admin**:
   - College ID: `ADM001`
   - Email: `admin@test.com`
   - Role: **Admin**
   - Password: `Admin123!@#`
3. Login with these credentials
4. **Check:** Dashboard shows "Pending Booking Requests" section ✅

### Test 2: Create Booking as Student
1. Register as **Student**:
   - College ID: `STU001`
   - Email: `student@test.com`
   - Role: **Student**
   - Password: `Test123!@#`
2. Login as student
3. Open browser console (F12) and run:
   ```javascript
   const token = localStorage.getItem('token');
   fetch('http://localhost:5000/api/bookings', {
     method: 'POST',
     headers: {
       'Content-Type': 'application/json',
       'Authorization': `Bearer ${token}`
     },
     body: JSON.stringify({
       lab_name: 'Test Lab',
       booking_date: '2024-12-25',
       start_time: '10:00',
       end_time: '12:00'
     })
   }).then(r => r.json()).then(console.log);
   ```
4. **Check:** Response shows `{success: true, booking_id: ...}` ✅

### Test 3: Verify RBAC (Role-Based Access)
1. Still logged in as **Student**
2. In browser console, run:
   ```javascript
   const token = localStorage.getItem('token');
   fetch('http://localhost:5000/api/bookings/pending', {
     headers: {'Authorization': `Bearer ${token}`}
   }).then(r => r.json()).then(console.log);
   ```
3. **Check:** Response shows `{message: "Insufficient permissions."}` with status 403 ✅
   - **This confirms RBAC is working!** Students cannot access admin endpoints.

### Test 4: Admin Approves Booking
1. Login as **Admin** (`ADM001`)
2. On dashboard, scroll to "Pending Booking Requests"
3. **Check:** You see the booking created by student ✅
4. Click "Approve" button
5. **Check:** Alert shows "Booking approved successfully!" ✅
6. **Check:** Booking status changes or disappears from pending list ✅

---

## ✅ RBAC Verification Checklist

**RBAC IS WORKING IF:**
- ✅ Students get **403 Forbidden** when accessing `/api/bookings/pending`
- ✅ Students get **403 Forbidden** when trying to approve/reject bookings
- ✅ Admin can access `/api/bookings/pending` successfully (200 OK)
- ✅ Admin can approve/reject bookings successfully (200 OK)
- ✅ Dashboard shows different content for Student vs Admin
- ✅ Unauthenticated requests get **401 Unauthorized**

**RBAC IS NOT WORKING IF:**
- ❌ Students can access admin endpoints (should be blocked)
- ❌ Admin cannot access admin endpoints (should work)
- ❌ Dashboard shows same content for all roles

---

## 📋 Full Testing Guide

For comprehensive testing instructions, see: **`MANUAL_TESTING_GUIDE.md`**

---

## 🐛 Troubleshooting

**Server not starting?**
- Check if port 5000 is already in use
- Make sure all dependencies are installed: `pip install -r requirements.txt`

**Tests failing?**
- Make sure server is running: `python app.py`
- Check database exists: `lab_reservations.db`
- Clear browser cache/localStorage

**RBAC not working?**
- Check authentication middleware in `app.py` (lines 221-244)
- Verify `@require_role("admin")` decorator is on admin endpoints
- Check JWT token includes role in payload

---

## 📊 Expected Test Results

| Test | Expected Result | Status |
|------|---------------|--------|
| Student accesses admin endpoint | 403 Forbidden | ✅ RBAC Working |
| Admin accesses admin endpoint | 200 OK | ✅ RBAC Working |
| Student creates booking | 201 Created | ✅ Working |
| Admin approves booking | 200 OK | ✅ Working |
| Unauthenticated access | 401 Unauthorized | ✅ Auth Working |

---

## 🎯 Quick Answer: Is RBAC Working?

**Run this one command:**
```bash
python verify_rbac.py
```

If all tests pass → **✅ YES, RBAC IS WORKING!**

If any test fails → Check the error message and see troubleshooting section.

