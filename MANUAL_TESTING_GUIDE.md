# Manual Testing Guide - Remote Lab Reservation System

## 🎯 Testing Checklist for Jira Story: "Approve or Reject Bookings"

This guide will help you verify that all features from your Jira story are working correctly, including role-based access control (RBAC).

---

## 📋 Prerequisites

1. **Start the Flask server:**
   ```bash
   python app.py
   ```
   Server should start on `http://localhost:5000`

2. **Clear browser data (optional but recommended):**
   - Open browser DevTools (F12)
   - Application tab → Clear Storage → Clear site data

---

## ✅ Test 1: Registration Flow with All Roles

### Test 1.1: Register as Student
1. Open `register.html` in browser
2. Fill in the form:
   - College ID: `STU001`
   - Name: `Test Student`
   - Email: `student@test.com`
   - Role: **Student**
   - Password: `Test123!@#`
3. Click "Register"
4. **Expected:** Success message, redirects to login page

### Test 1.2: Register as Admin
1. Open `register.html` in browser
2. Fill in the form:
   - College ID: `ADM001`
   - Name: `Test Admin`
   - Email: `admin@test.com`
   - Role: **Admin**
   - Password: `Admin123!@#`
3. Click "Register"
4. **Expected:** Success message, redirects to login page

### Test 1.3: Register as Lab Assistant
1. Open `register.html` in browser
2. Fill in the form:
   - College ID: `LAB001`
   - Name: `Test Lab Assistant`
   - Email: `lab@test.com`
   - Role: **Lab Assistant**
   - Password: `Lab123!@#`
3. Click "Register"
4. **Expected:** Success message, redirects to login page

### Test 1.4: Register as Faculty
1. Open `register.html` in browser
2. Fill in the form:
   - College ID: `FAC001`
   - Name: `Test Faculty`
   - Email: `faculty@test.com`
   - Role: **Faculty**
   - Password: `Fac123!@#`
3. Click "Register"
4. **Expected:** Success message, redirects to login page

---

## ✅ Test 2: Login Flow & JWT Authentication

### Test 2.1: Login as Student
1. Open `login.html`
2. Enter:
   - College ID: `STU001`
   - Password: `Test123!@#`
3. Click "Login"
4. **Expected:** 
   - Redirects to dashboard
   - Shows "Welcome, Test Student!"
   - Role badge shows "STUDENT"
   - Only student-accessible features visible

### Test 2.2: Login as Admin
1. Open `login.html` (or logout first)
2. Enter:
   - College ID: `ADM001`
   - Password: `Admin123!@#`
3. Click "Login"
4. **Expected:**
   - Redirects to dashboard
   - Shows "Welcome, Test Admin! You have administrative access."
   - Role badge shows "ADMIN"
   - Admin-only sections visible (Manage Users, Manage Labs, Reports)
   - **Pending Booking Requests** section visible

### Test 2.3: Verify Token Storage
1. After logging in, open DevTools (F12)
2. Go to Application → Local Storage → `http://localhost:5000`
3. **Expected:**
   - `token` key exists with JWT value
   - `user` key exists with user data JSON

---

## ✅ Test 3: Role-Based Dashboard Access

### Test 3.1: Student Dashboard
1. Login as Student (`STU001`)
2. **Expected Dashboard Elements:**
   - ✅ "Reserve Lab" card visible
   - ✅ "My Reservations" card visible
   - ✅ "Available Labs" card visible
   - ❌ "Manage Users" card **NOT visible**
   - ❌ "Manage Labs" card **NOT visible**
   - ❌ "Reports" card **NOT visible**
   - ✅ "My Bookings" section visible at bottom

### Test 3.2: Admin Dashboard
1. Login as Admin (`ADM001`)
2. **Expected Dashboard Elements:**
   - ✅ "Reserve Lab" card visible
   - ✅ "My Reservations" card visible
   - ✅ "Available Labs" card visible
   - ✅ "Manage Users" card visible
   - ✅ "Manage Labs" card visible
   - ✅ "Reports" card visible
   - ✅ "Pending Booking Requests" section visible at bottom

### Test 3.3: Lab Assistant Dashboard
1. Login as Lab Assistant (`LAB001`)
2. **Expected Dashboard Elements:**
   - ✅ "Reserve Lab" card visible
   - ✅ "My Reservations" card visible
   - ✅ "Available Labs" card visible
   - ❌ Admin-only cards **NOT visible**

---

## ✅ Test 4: Booking Creation (Student)

### Test 4.1: Create Booking Request
1. Login as Student (`STU001`)
2. Open browser DevTools → Console tab
3. Run this JavaScript to create a booking:
   ```javascript
   const token = localStorage.getItem('token');
   fetch('http://localhost:5000/api/bookings', {
     method: 'POST',
     headers: {
       'Content-Type': 'application/json',
       'Authorization': `Bearer ${token}`
     },
     body: JSON.stringify({
       lab_name: 'Computer Lab A',
       booking_date: '2024-12-25',
       start_time: '10:00',
       end_time: '12:00'
     })
   })
   .then(r => r.json())
   .then(data => console.log('Booking created:', data));
   ```
4. **Expected:**
   - Response: `{success: true, booking_id: <number>, message: "..."}`
   - Status code: 201

### Test 4.2: Verify Booking Appears in Dashboard
1. Refresh the dashboard page
2. Scroll to "My Bookings" section
3. **Expected:**
   - Booking appears in table
   - Status shows "pending"
   - Lab name, date, time visible

### Test 4.3: Create Booking Without Auth (Should Fail)
1. Open new incognito/private window
2. Run the same fetch command (without token)
3. **Expected:**
   - Response: `{message: "Missing or invalid Authorization header."}`
   - Status code: 401

---

## ✅ Test 5: Role-Based API Access

### Test 5.1: Student Cannot Access Admin Endpoints
1. Login as Student (`STU001`)
2. Open DevTools Console
3. Run:
   ```javascript
   const token = localStorage.getItem('token');
   fetch('http://localhost:5000/api/bookings/pending', {
     headers: {'Authorization': `Bearer ${token}`}
   })
   .then(r => r.json())
   .then(data => console.log('Response:', data));
   ```
4. **Expected:**
   - Response: `{message: "Insufficient permissions."}`
   - Status code: 403 ❌ **This confirms RBAC is working!**

### Test 5.2: Student Cannot Approve Bookings
1. Still logged in as Student
2. Run:
   ```javascript
   const token = localStorage.getItem('token');
   fetch('http://localhost:5000/api/bookings/1/approve', {
     method: 'POST',
     headers: {'Authorization': `Bearer ${token}`}
   })
   .then(r => r.json())
   .then(data => console.log('Response:', data));
   ```
3. **Expected:**
   - Response: `{message: "Insufficient permissions."}`
   - Status code: 403 ❌ **RBAC working!**

### Test 5.3: Admin CAN Access Admin Endpoints
1. Login as Admin (`ADM001`)
2. Run:
   ```javascript
   const token = localStorage.getItem('token');
   fetch('http://localhost:5000/api/bookings/pending', {
     headers: {'Authorization': `Bearer ${token}`}
   })
   .then(r => r.json())
   .then(data => console.log('Pending bookings:', data));
   ```
3. **Expected:**
   - Response: `{success: true, bookings: [...]}`
   - Status code: 200 ✅ **Admin access confirmed!**

---

## ✅ Test 6: Booking Approval System (Admin)

### Test 6.1: View Pending Bookings
1. Login as Admin (`ADM001`)
2. On dashboard, scroll to "Pending Booking Requests" section
3. **Expected:**
   - Table shows booking created by student
   - Status column shows "pending"
   - Approve and Reject buttons visible

### Test 6.2: Approve Booking
1. Still on admin dashboard
2. Click "Approve" button for the pending booking
3. **Expected:**
   - Alert: "Booking approved successfully!"
   - Table refreshes
   - Booking status changes to "approved" (or disappears if filtered)

### Test 6.3: Verify Approval in Database
1. Open DevTools Console
2. Run:
   ```javascript
   const token = localStorage.getItem('token');
   fetch('http://localhost:5000/api/bookings', {
     headers: {'Authorization': `Bearer ${token}`}
   })
   .then(r => r.json())
   .then(data => {
     console.log('All bookings:', data.bookings);
     const approved = data.bookings.find(b => b.status === 'approved');
     console.log('Approved booking:', approved);
   });
   ```
3. **Expected:**
   - Booking with status "approved" exists
   - `updated_at` field has timestamp

### Test 6.4: Create Another Booking & Reject It
1. Login as Student (`STU001`)
2. Create another booking (use Test 4.1 method)
3. Login as Admin (`ADM001`)
4. Click "Reject" button
5. Confirm rejection in dialog
6. **Expected:**
   - Alert: "Booking rejected successfully!"
   - Booking status changes to "rejected"

### Test 6.5: Verify Student Sees Updated Status
1. Login as Student (`STU001`)
2. Check "My Bookings" section
3. **Expected:**
   - Approved booking shows "approved" status
   - Rejected booking shows "rejected" status

---

## ✅ Test 7: Authentication Middleware

### Test 7.1: Access Protected Endpoint Without Token
1. Open new incognito window
2. Run:
   ```javascript
   fetch('http://localhost:5000/api/bookings')
     .then(r => r.json())
     .then(data => console.log('Response:', data));
   ```
3. **Expected:**
   - Response: `{message: "Missing or invalid Authorization header."}`
   - Status code: 401 ✅ **Auth middleware working!**

### Test 7.2: Access with Invalid Token
1. Run:
   ```javascript
   fetch('http://localhost:5000/api/bookings', {
     headers: {'Authorization': 'Bearer invalid.token.here'}
   })
   .then(r => r.json())
   .then(data => console.log('Response:', data));
   ```
2. **Expected:**
   - Response: `{message: "Invalid token."}`
   - Status code: 401 ✅ **Token validation working!**

### Test 7.3: Access with Expired Token
1. Login as Student
2. Wait 1 hour (or modify token expiry in code)
3. Try to access bookings
4. **Expected:**
   - Response: `{message: "Token expired."}`
   - Status code: 401 ✅ **Token expiry working!**

---

## ✅ Test 8: Database Operations

### Test 8.1: Verify Bookings Table Created
1. Check if `lab_reservations.db` file exists
2. Open database (use SQLite browser or command line):
   ```bash
   sqlite3 lab_reservations.db
   .tables
   ```
3. **Expected:**
   - `users` table exists
   - `bookings` table exists ✅

### Test 8.2: Verify Foreign Key Relationship
1. In SQLite:
   ```sql
   SELECT b.id, b.college_id, u.name, b.status 
   FROM bookings b 
   JOIN users u ON b.college_id = u.college_id;
   ```
2. **Expected:**
   - Returns bookings with user names
   - No orphaned bookings ✅

---

## ✅ Test 9: Input Validation

### Test 9.1: Invalid Date Format
1. Login as Student
2. Try to create booking with invalid date:
   ```javascript
   const token = localStorage.getItem('token');
   fetch('http://localhost:5000/api/bookings', {
     method: 'POST',
     headers: {
       'Content-Type': 'application/json',
       'Authorization': `Bearer ${token}`
     },
     body: JSON.stringify({
       lab_name: 'Lab A',
       booking_date: 'invalid-date',
       start_time: '10:00',
       end_time: '12:00'
     })
   })
   .then(r => r.json())
   .then(data => console.log('Response:', data));
   ```
3. **Expected:**
   - Response: `{message: "Invalid date or time format."}`
   - Status code: 400 ✅

### Test 9.2: Missing Required Fields
1. Try to create booking with missing fields:
   ```javascript
   fetch('http://localhost:5000/api/bookings', {
     method: 'POST',
     headers: {
       'Content-Type': 'application/json',
       'Authorization': `Bearer ${token}`
     },
     body: JSON.stringify({
       lab_name: 'Lab A'
       // Missing other fields
     })
   })
   .then(r => r.json())
   .then(data => console.log('Response:', data));
   ```
2. **Expected:**
   - Response: `{message: "Missing required fields."}`
   - Status code: 400 ✅

---

## ✅ Test 10: Role Validation

### Test 10.1: Invalid Role Registration
1. Open `register.html`
2. Try to register with invalid role using DevTools:
   ```javascript
   fetch('http://localhost:5000/api/register', {
     method: 'POST',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({
       college_id: 'INV001',
       name: 'Invalid',
       email: 'inv@test.com',
       password: 'Test123!@#',
       role: 'invalid_role'
     })
   })
   .then(r => r.json())
   .then(data => console.log('Response:', data));
   ```
2. **Expected:**
   - Response: `{message: "Validation failed: Invalid role..."}`
   - Status code: 400 ✅

---

## 📊 Summary Checklist

### RBAC Verification:
- [ ] Student cannot access admin endpoints (403 error)
- [ ] Admin can access all endpoints (200 success)
- [ ] Lab Assistant has limited access
- [ ] Faculty has limited access
- [ ] Dashboard shows role-appropriate content
- [ ] Authentication middleware blocks unauthorized access

### Booking Approval System:
- [ ] Students can create booking requests
- [ ] Bookings start with "pending" status
- [ ] Admin can view pending bookings
- [ ] Admin can approve bookings
- [ ] Admin can reject bookings
- [ ] Status updates reflect in database
- [ ] Dashboard refreshes after approval/rejection

### Authentication:
- [ ] JWT tokens are generated on login
- [ ] Tokens are validated on protected routes
- [ ] Expired tokens are rejected
- [ ] Invalid tokens are rejected
- [ ] Missing tokens return 401

### Database:
- [ ] Bookings table created
- [ ] Foreign key relationships work
- [ ] Status updates persist
- [ ] Timestamps are recorded

---

## 🐛 Troubleshooting

### If tests fail:

1. **Check server is running:**
   ```bash
   python app.py
   ```

2. **Check database exists:**
   - File: `lab_reservations.db` should exist
   - Tables: `users` and `bookings` should exist

3. **Clear browser cache:**
   - DevTools → Application → Clear Storage

4. **Check console for errors:**
   - DevTools → Console tab

5. **Verify token in localStorage:**
   ```javascript
   console.log(localStorage.getItem('token'));
   ```

---

## ✅ Expected Results Summary

| Feature | Expected Behavior | Status |
|---------|------------------|--------|
| Student Registration | ✅ Success | |
| Admin Registration | ✅ Success | |
| Lab Assistant Registration | ✅ Success | |
| Student Login | ✅ JWT token generated | |
| Admin Login | ✅ JWT token generated | |
| Student Dashboard | ✅ Limited features visible | |
| Admin Dashboard | ✅ All features + pending bookings | |
| Student Creates Booking | ✅ Status: pending | |
| Student Views Own Bookings | ✅ Only their bookings | |
| Student Accesses Admin Endpoint | ❌ 403 Forbidden | |
| Admin Views Pending Bookings | ✅ All pending bookings | |
| Admin Approves Booking | ✅ Status: approved | |
| Admin Rejects Booking | ✅ Status: rejected | |
| Auth Middleware | ✅ Blocks unauthorized | |
| Token Validation | ✅ Validates JWT | |

---

## 🎯 Role-Based Access Verification

**✅ RBAC IS WORKING IF:**
1. Students get 403 when accessing `/api/bookings/pending`
2. Students get 403 when accessing `/api/bookings/<id>/approve`
3. Admin can access all endpoints successfully
4. Dashboard shows different content based on role
5. Unauthenticated users get 401 on protected routes

**❌ RBAC IS NOT WORKING IF:**
1. Students can access admin endpoints (should be 403)
2. Admin cannot access admin endpoints (should be 200)
3. Dashboard shows same content for all roles
4. No authentication required for protected routes

---

## 📝 Notes

- All API endpoints require Bearer token in Authorization header
- Token format: `Bearer <jwt_token>`
- Bookings are created with status "pending" by default
- Only admins can approve/reject bookings
- Students can only see their own bookings
- Admins can see all bookings

