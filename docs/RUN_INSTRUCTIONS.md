# 🚀 How to Run the Application

## Step-by-Step Instructions

### **TERMINAL 1: Start Backend Server**

1. **Open PowerShell or Command Prompt**
   - Press `Win + X` and select "Terminal" or "PowerShell"
   - Or search for "PowerShell" in Start Menu

2. **Navigate to the project directory:**
   ```powershell
   cd "C:\Users\gouri\Desktop\PESU_RR_CSE_D_P32_Remote_Lab_Reservation_System_Dream-team"
   ```

3. **Make sure dependencies are installed:**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Start the Flask backend server:**
   ```powershell
   python app.py
   ```

   You should see output like:
   ```
   Using database file: C:\Users\gouri\Desktop\...\lab_reservations.db
   Initializing database...
   Database initialization complete.
   * Running on http://127.0.0.1:5000
   ```

   **⚠️ IMPORTANT: Keep this terminal window open!** The server must stay running.

---

### **BROWSER: Access the Frontend**

5. **Open your web browser** (Chrome, Firefox, Edge, etc.)

6. **Navigate to the registration page:**
   ```
   http://localhost:5000/register.html
   ```

7. **Create an Admin Account:**
   - College ID: `ADMIN001`
   - Name: `Admin User`
   - Email: `admin@pesu.edu`
   - Password: `Admin123!` (must have 8+ chars, 1 number, 1 symbol)
   - Role: Select `admin`
   - Click "Register"

8. **Login:**
   - Go to: `http://localhost:5000/login.html`
   - College ID: `ADMIN001`
   - Password: `Admin123!`
   - Click "Login"

9. **Access Dashboard:**
   - After login, you'll be redirected to: `http://localhost:5000/dashboard.html`

---

### **Testing Lab Management Feature**

10. **On the Dashboard:**
    - You should see a card with "🏪 Manage Labs"
    - Click on the **"Manage Labs"** card

11. **Add a New Lab:**
    - Click the **"+ Add New Lab"** button
    - Fill in the form:
      - **Lab Name:** `Computer Lab 1`
      - **Capacity:** `30`
      - **Equipment:** `["Computer", "Projector", "Whiteboard"]`
        - Or as comma-separated: `Computer, Projector, Whiteboard`
    - Click **"Save Lab"**

12. **Edit a Lab:**
    - In the labs table, click the **"Edit"** button next to any lab
    - Modify the fields
    - Click **"Save Lab"**

13. **Delete a Lab:**
    - Click the **"Delete"** button next to any lab
    - Confirm the deletion
    - The lab and its availability slots will be deleted

---

## 📋 Quick Test Checklist

- [ ] Backend server running on `http://localhost:5000`
- [ ] Can access `http://localhost:5000/register.html`
- [ ] Created admin account successfully
- [ ] Can login at `http://localhost:5000/login.html`
- [ ] Dashboard loads at `http://localhost:5000/dashboard.html`
- [ ] "Manage Labs" card is visible (admin only)
- [ ] Can create a new lab
- [ ] Can view list of labs
- [ ] Can edit a lab
- [ ] Can delete a lab
- [ ] Changes reflect immediately in the UI

---

## 🛠️ Troubleshooting

### **Port 5000 Already in Use:**
If you see `Address already in use`, either:
- Close the other application using port 5000, OR
- Change the port in `app.py` line 909:
  ```python
  app.run(debug=debug_mode, port=5001)  # Change to 5001 or any free port
  ```
  Then access: `http://localhost:5001/register.html`

### **Module Not Found Errors:**
Run:
```powershell
pip install -r requirements.txt
```

### **Database Errors:**
The database file (`lab_reservations.db`) will be created automatically on first run.
If you want to start fresh, delete this file and restart the server.

### **CORS Errors in Browser Console:**
Make sure you're accessing via `localhost` or `127.0.0.1`, not `file://`

---

## 🌐 All Available Pages

- `http://localhost:5000/` - Home page
- `http://localhost:5000/register.html` - User registration
- `http://localhost:5000/login.html` - User login
- `http://localhost:5000/dashboard.html` - User dashboard (requires login)

---

## 📝 API Endpoints (for testing with tools like Postman)

- `POST /api/register` - Register new user
- `POST /api/login` - Login and get JWT token
- `GET /api/me` - Get current user info (requires Bearer token)
- `GET /api/labs` - Get all labs (requires Bearer token)
- `POST /api/labs` - Create lab (admin only, requires Bearer token)
- `GET /api/labs/<id>` - Get specific lab (requires Bearer token)
- `PUT /api/labs/<id>` - Update lab (admin only, requires Bearer token)
- `DELETE /api/labs/<id>` - Delete lab (admin only, requires Bearer token)

---

## ✅ Success Indicators

When everything is working:
- ✅ Terminal shows: `* Running on http://127.0.0.1:5000`
- ✅ Browser can load `http://localhost:5000/register.html`
- ✅ Can register and login successfully
- ✅ Dashboard shows admin features
- ✅ Can create/edit/delete labs without errors

