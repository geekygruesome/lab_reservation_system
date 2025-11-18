# 🔐 How to Test Login - Step by Step

## ⚠️ IMPORTANT: Server Must Be Running First!

1. **Start the Flask server:**
   ```powershell
   python app.py
   ```
   You should see: `* Running on http://127.0.0.1:5000`

2. **Keep the server running** - Don't close this terminal!

---

## 🧪 Test Login with Pre-created Accounts

### Option 1: Test Admin Account (Recommended)

1. Open browser and go to: `http://localhost:5000/login.html`

2. Enter these credentials:
   - **College ID:** `ADM001`
   - **Password:** `Admin123!@#`

3. Click "Login"

4. **Expected Result:**
   - ✅ You should be redirected to dashboard
   - ✅ You should see "Welcome, Test Admin! You have administrative access."
   - ✅ You should see admin-only cards (Manage Users, Manage Labs, Reports)
   - ✅ Pending Booking Requests section should be visible

---

### Option 2: Test Student Account

1. Go to: `http://localhost:5000/login.html`

2. Enter these credentials:
   - **College ID:** `STU001`
   - **Password:** `Test123!@#`

3. Click "Login"

4. **Expected Result:**
   - ✅ Redirected to dashboard
   - ✅ Welcome message shows "Test Student"
   - ✅ Only student features visible (no admin cards)

---

### Option 3: Register New Account

1. Go to: `http://localhost:5000/register.html`

2. Fill in the form:
   - **College ID:** `MYTEST001`
   - **Name:** `My Test User`
   - **Email:** `mytest@test.com`
   - **Role:** `admin` (or any role you want)
   - **Password:** `MyTest123!` (must have 8+ chars, 1 number, 1 symbol)

3. Click "Register"

4. Wait for success message, then you'll be redirected to login

5. Login with the credentials you just created

---

## 🐛 Troubleshooting Login Issues

### Issue 1: "Network error" or Can't connect
**Solution:**
- ✅ Make sure `python app.py` is running
- ✅ Check terminal shows: `* Running on http://127.0.0.1:5000`
- ✅ Make sure you're using `http://localhost:5000` (not `https://`)

### Issue 2: "Invalid credentials"
**Solution:**
- ✅ Check you're using the exact College ID (case-sensitive)
- ✅ Check password is correct (including special characters)
- ✅ Make sure the user exists in database

### Issue 3: Login succeeds but doesn't redirect
**Solution:**
- ✅ Open browser console (F12 → Console tab)
- ✅ Check for JavaScript errors
- ✅ Try manually going to: `http://localhost:5000/dashboard.html`

### Issue 4: "Token not found" on dashboard
**Solution:**
- ✅ Check browser console (F12)
- ✅ Go to Application → Local Storage → `http://localhost:5000`
- ✅ Should see `token` and `user` keys
- ✅ If missing, login again

---

## 🔍 Debugging Steps

### Step 1: Check Browser Console
1. Open `http://localhost:5000/login.html`
2. Press **F12** to open Developer Tools
3. Go to **Console** tab
4. Try to login
5. Look for any red error messages

### Step 2: Check Network Requests
1. In Developer Tools, go to **Network** tab
2. Try to login
3. Look for a request to `/api/login`
4. Click on it to see:
   - **Status:** Should be 200 for success, 401 for invalid credentials
   - **Response:** Should show JSON with `token` and `success: true`

### Step 3: Check Server Logs
Look at the terminal where `python app.py` is running. You should see:
```
127.0.0.1 - - [DATE] "POST /api/login HTTP/1.1" 200 -
```

If you see `401` instead of `200`, the credentials are wrong.

---

## ✅ Quick Test Checklist

- [ ] Flask server is running (`python app.py`)
- [ ] Can access `http://localhost:5000/login.html`
- [ ] Browser console shows no errors (F12)
- [ ] Using correct College ID (case-sensitive)
- [ ] Using correct password (with special characters)
- [ ] User exists in database
- [ ] After login, redirected to dashboard
- [ ] Token stored in localStorage (check DevTools → Application)

---

## 📝 Pre-created Test Accounts

These accounts are already in your database:

| College ID | Password | Role | Purpose |
|------------|----------|------|---------|
| `ADM001` | `Admin123!@#` | admin | Test admin features |
| `STU001` | `Test123!@#` | student | Test student features |
| `LAB001` | `Lab123!@#` | lab_assistant | Test lab assistant features |
| `FAC001` | `Fac123!@#` | faculty | Test faculty features |

---

## 🎯 What Should Happen After Login

1. **For Admin:**
   - Dashboard shows all cards including "Manage Labs"
   - "Pending Booking Requests" section visible
   - Can access `/api/bookings/pending` endpoint

2. **For Student:**
   - Dashboard shows basic cards only
   - "My Bookings" section visible
   - Cannot access admin endpoints (403 error)

3. **Token Storage:**
   - Check DevTools → Application → Local Storage
   - Should see `token` (JWT string)
   - Should see `user` (JSON with college_id, role, name)

---

## 💡 Still Having Issues?

1. **Clear browser cache:**
   - DevTools → Application → Clear Storage → Clear site data

2. **Check database:**
   ```powershell
   python -c "import sqlite3; conn = sqlite3.connect('lab_reservations.db'); cursor = conn.cursor(); cursor.execute('SELECT college_id, email, role FROM users'); print('\n'.join([f'{r[0]} - {r[2]}' for r in cursor.fetchall()])); conn.close()"
   ```

3. **Create fresh test user:**
   ```powershell
   python create_test_users.py
   ```

4. **Restart the server:**
   - Press `CTRL + C` in the terminal
   - Run `python app.py` again

