@echo off
REM Quick Start Script for Windows Command Prompt
REM Starts the Flask backend server

echo.
echo ===================================
echo   Starting Lab Reservation System
echo ===================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.11+
    pause
    exit /b 1
)

echo [OK] Python found
echo.

REM Check if dependencies are installed
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Dependencies not found. Installing...
    pip install -r requirements.txt
)

echo.
echo Starting Flask server...
echo Server will be available at: http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo.

REM Start the Flask application
python app.py

pause

