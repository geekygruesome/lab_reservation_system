# How to Run the Application

## 🚀 Quick Start

### Option 1: Run Everything (Recommended)
```powershell
# Start the Flask backend server
python app.py
```

The application will be available at: **http://localhost:5000**

---

## 📋 Detailed Instructions

### Backend (Flask Server)

#### Windows PowerShell
```powershell
# Navigate to project directory
cd "C:\Users\gurleen kaur\lab_reservation_system\lab_reservation_system"

# Activate virtual environment (if using one)
.\venv\Scripts\Activate.ps1

# Install dependencies (first time only)
pip install -r requirements.txt

# Run the Flask application
python app.py
```

#### Alternative: Using npm script
```powershell
npm start
```

#### Linux/Mac
```bash
# Navigate to project directory
cd /path/to/lab_reservation_system

# Activate virtual environment (if using one)
source venv/bin/activate

# Install dependencies (first time only)
pip install -r requirements.txt

# Run the Flask application
python app.py
```

### Frontend (HTML Pages)

The frontend is served automatically by Flask. Once the backend is running, access:

- **Home/Index:** http://localhost:5000/
- **Registration:** http://localhost:5000/register.html
- **Login:** http://localhost:5000/login.html
- **Dashboard:** http://localhost:5000/dashboard.html
- **Available Labs:** http://localhost:5000/available_labs.html
- **Admin Labs:** http://localhost:5000/admin_available_labs.html (Admin only)
- **Lab Assistant Labs:** http://localhost:5000/lab_assistant_labs.html (Lab Assistant only)

---

## 🔧 Environment Setup

### First Time Setup

1. **Install Python Dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

2. **Install Node.js Dependencies (optional, for npm scripts)**
   ```powershell
   npm install
   ```

3. **Create Test Users (optional)**
   ```powershell
   python create_test_users.py
   ```

### Environment Variables (Optional)

Create a `.env` file or set environment variables:

```powershell
# PowerShell
$env:SECRET_KEY = "your-secret-key-here"
$env:JWT_EXP_DELTA_SECONDS = "3600"
$env:FLASK_DEBUG = "False"
```

Or in Command Prompt:
```cmd
set SECRET_KEY=your-secret-key-here
set JWT_EXP_DELTA_SECONDS=3600
set FLASK_DEBUG=False
```

---

## 🌐 Accessing the Application

Once the server is running, you'll see:
```
Using database file: C:\Users\...\data\lab_reservations.db
Initializing database...
Database initialization complete.
 * Running on http://127.0.0.1:5000
```

### Open in Browser

1. Open your web browser
2. Navigate to: **http://localhost:5000**
3. Or use: **http://127.0.0.1:5000**

---

## 📱 Application Pages

### Public Pages
- **/** - Home page (index.html)
- **/register.html** - User registration
- **/login.html** - User login

### Protected Pages (Require Authentication)
- **/dashboard.html** - User dashboard (role-based)
- **/available_labs.html** - View available labs (Students/Faculty)
- **/admin_available_labs.html** - Admin lab management
- **/lab_assistant_labs.html** - Lab assistant assigned labs

---

## 🧪 Test Users

If you created test users, you can login with:

| Role | College ID | Password | Email |
|------|-----------|----------|-------|
| Student | STU001 | Test123!@# | student@test.com |
| Admin | ADM001 | Admin123!@# | admin@test.com |
| Lab Assistant | LAB001 | Lab123!@# | lab@test.com |
| Faculty | FAC001 | Fac123!@# | faculty@test.com |

---

## 🛑 Stopping the Server

To stop the Flask server:
- Press `Ctrl + C` in the terminal

---

## 🐛 Troubleshooting

### Port Already in Use
If port 5000 is already in use:
```powershell
# Find process using port 5000
netstat -ano | findstr :5000

# Kill the process (replace PID with actual process ID)
taskkill /PID <PID> /F
```

Or change the port in `app.py`:
```python
app.run(debug=debug_mode, port=5001)  # Change to 5001
```

### Database Issues
```powershell
# Check database
python tools/check_db.py

# Recreate database (WARNING: Deletes all data)
Remove-Item data\lab_reservations.db
python app.py  # Will recreate database
```

### Dependencies Missing
```powershell
# Reinstall all dependencies
pip install -r requirements.txt --force-reinstall
```

### Module Not Found
```powershell
# Make sure you're in the project directory
cd "C:\Users\gurleen kaur\lab_reservation_system\lab_reservation_system"

# Verify Python path
python --version
pip list
```

---

## 📊 API Endpoints

While the server is running, you can also access API endpoints:

- **POST** http://localhost:5000/api/register - Register new user
- **POST** http://localhost:5000/api/login - Login and get JWT token
- **GET** http://localhost:5000/api/me - Get current user info (requires Bearer token)
- **GET** http://localhost:5000/api/labs - Get all labs (requires auth)
- **POST** http://localhost:5000/api/bookings - Create booking (requires auth)

Use tools like Postman or curl to test API endpoints.

---

## 🔄 Development Mode

For development with auto-reload:

```powershell
# Set environment variable
$env:FLASK_DEBUG = "True"

# Run the app
python app.py
```

Or modify `app.py` temporarily:
```python
app.run(debug=True, port=5000)
```

**Note:** Never use `debug=True` in production!

---

## 📝 Quick Commands Summary

```powershell
# Start server
python app.py

# Start server (using npm)
npm start

# Create test users
python create_test_users.py

# Check database
python tools/check_db.py

# Stop server
Ctrl + C
```

---

## 🌍 Accessing from Other Devices

To access from other devices on the same network:

1. Find your local IP address:
   ```powershell
   ipconfig
   # Look for IPv4 Address (e.g., 192.168.1.100)
   ```

2. Update `app.py`:
   ```python
   app.run(debug=debug_mode, host='0.0.0.0', port=5000)
   ```

3. Access from other device:
   ```
   http://192.168.1.100:5000
   ```

**Warning:** Only do this on trusted networks!

---

## ✅ Verification Checklist

Before running, ensure:
- [ ] Python 3.11+ is installed
- [ ] All dependencies are installed (`pip install -r requirements.txt`)
- [ ] You're in the project root directory
- [ ] Database directory exists (`data/` folder)
- [ ] Port 5000 is available

---

**Last Updated:** November 2025

