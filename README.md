# Remote Lab Reservation System

**Project ID:** P32  
**Course:** UE23CS341A  
**Academic Year:** 2025  
**Semester:** 5th Sem  
**Campus:** RR  
**Branch:** CSE  
**Section:** D  
**Team:** Dream team

## 📋 Project Description

A web-based lab reservation system that allows students to book lab slots, check availability, and receive confirmations. The system includes user authentication with JWT tokens, role-based access control, and a responsive web interface.

**Key Features:**
- User registration and JWT-based authentication
- Role-based access control (Student/Faculty/Admin)
- Lab reservation booking and management
- Responsive dashboard with role-specific options
- Comprehensive test coverage (87%+)
- CI/CD pipeline with automated testing and linting

## 🧑‍💻 Development Team (Dream team)

- [@geekygruesome](https://github.com/geekygruesome) - Scrum Master
- [@Deepa-15](https://github.com/Deepa-15) - Developer Team
- [@gourimh](https://github.com/gourimh) - Developer Team
- [@atkdishitha12-beep](https://github.com/atkdishitha12-beep) - Developer Team

## 👨‍🏫 Teaching Assistant

- [@Crashbadger24](https://github.com/Crashbadger24)
- [@Srujkul](https://github.com/Srujkul)
- [@srishmath](https://github.com/srishmath)

## 👨‍⚖️ Faculty Supervisor

- [@sapnavm](https://github.com/sapnavm)

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- pip (Python package manager)
- Modern web browser

### Installation

1. Clone the repository
   ```bash
   git clone https://github.com/pestechnology/PESU_RR_CSE_D_P32_Remote_Lab_Reservation_System_Dream-team.git
   cd PESU_RR_CSE_D_P32_Remote_Lab_Reservation_System_Dream-team
   ```

2. Create a virtual environment (optional but recommended)
   ```bash
   python -m venv venv
   # On Windows
   venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application
   ```bash
   # Using Python directly
   python app.py
   
   # Or using npm script
   npm start
   ```

   The application will start on `http://localhost:5000`

5. (Optional) Create test users
   ```bash
   python create_test_users.py
   ```

6. Access the application
   - Open your browser and go to: `http://localhost:5000`
   - Frontend pages are automatically served by Flask:
     - Home: `http://localhost:5000/`
     - Register: `http://localhost:5000/register.html`
     - Login: `http://localhost:5000/login.html`
     - Dashboard: `http://localhost:5000/dashboard.html`

### Usage

1. **Registration**: Visit `http://localhost:5000/register.html` to create a new account
   - College ID: Unique identifier (alphanumeric)
   - Email: Valid email address
   - Password: Min 8 characters, 1 number, 1 symbol
   - Role: Student or Faculty

2. **Login**: Go to `http://localhost:5000/login.html` with your credentials

3. **Dashboard**: After login, you'll see your personalized dashboard
   - Students see basic reservation options
   - Admin users see additional management features

## 📁 Project Structure

```
PESU_RR_CSE_D_P32_Remote_Lab_Reservation_System_Dream-team/
├── app.py                    # Main Flask application
├── requirements.txt          # Python dependencies
├── package.json              # Node.js scripts and dependencies
├── setup.cfg                 # Flake8 configuration
├── pytest.ini                # Pytest configuration
├── calculate_lint_score.py   # Lint score calculator
├── create_test_users.py      # Test user creation script
├── templates/                # HTML templates (Flask convention)
│   ├── index.html
│   ├── register.html
│   ├── login.html
│   ├── dashboard.html
│   ├── available_labs.html
│   ├── admin_available_labs.html
│   └── lab_assistant_labs.html
├── data/                     # Database files
│   └── lab_reservations.db
├── docs/                     # Documentation files
│   ├── README.md
│   ├── QUICKSTART.md
│   ├── MANUAL_TESTING_GUIDE.md
│   └── ... (other docs)
├── reports/                  # Test reports and coverage
│   ├── coverage.xml
│   └── bandit-report.json
├── tests/                    # Test suite
│   ├── __init__.py
│   ├── test_authentication_clean.py
│   ├── test_available_labs.py
│   └── ... (other tests)
├── tools/                    # Utility scripts
│   ├── check_db.py
│   └── debug_register.py
├── .github/
│   └── workflows/
│       └── ci-cd.yml         # 5-stage CI/CD pipeline
└── README.md                 # This file
```

## 🏗️ Architecture

### Backend (Flask)
- **Authentication**: JWT (HS256) with expiry tokens
- **Database**: SQLite3 with secure password hashing
- **API Endpoints**:
  - `POST /api/register` - User registration
  - `POST /api/login` - User authentication
  - `GET /api/me` - Get current user info (requires Bearer token)

### Frontend
- **HTML/CSS/JavaScript**: Vanilla JS with responsive design
- **Token Storage**: localStorage (JWT token management)
- **Role-Based UI**: Conditional rendering based on user role

## 🔐 Security Features

- ✅ Password hashing with werkzeug security
- ✅ JWT-based session management
- ✅ CORS enabled for API safety
- ✅ Input validation and sanitization
- ✅ CSRF protection ready
- ✅ No hardcoded secrets (uses environment variables)
- ✅ Environment-based debug mode

## 🧪 Testing

### Run Tests
```bash
# Run all tests with coverage
python -m pytest tests/ -v --cov=app --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_authentication_clean.py -v

# Run with coverage report (HTML)
python -m pytest tests/ --cov=app --cov-report=html

# Run with coverage XML (for CI/CD)
python -m pytest tests/ --cov=app --cov-report=xml --cov-report=term-missing

# Check coverage threshold (≥75%)
python -m pytest tests/ --cov=app --cov-fail-under=75
```

### Test Coverage
Current coverage: **87%** (22 tests passing)

Tests cover:
- User registration (valid/invalid inputs, duplicates)
- User login (valid/invalid credentials)
- JWT authentication and token expiry
- Error handling and edge cases
- Database operations and constraints

## 🔍 Code Quality

### Linting
```bash
# Run flake8 linting
python -m flake8 app.py tests/ --count --statistics --max-line-length=120

# Calculate lint score (must be ≥7.5/10)
python calculate_lint_score.py

# Or using npm script
npm run lint
```

Status: ✅ **Flake8 passing** (0 violations, Score: 10/10)

### Security
```bash
# Run Bandit security check
python -m bandit -r app.py -ll

# Generate security report (JSON)
python -m bandit -r app.py -ll -f json -o reports/bandit-report.json

# Run npm security audit
npm audit --audit-level=high
```

## 🚢 Deployment & CI/CD

### 5-Stage CI/CD Pipeline

The project uses a comprehensive 5-stage CI/CD pipeline that runs automatically on every push and pull request:

**Pipeline File:** `.github/workflows/ci-cd.yml`

#### Stage 1: Build 🔨
- Sets up Python (3.11, 3.12) and Node.js environments
- Installs all dependencies (Python and Node.js)
- Verifies build integrity
- Creates build artifacts

#### Stage 2: Lint 🔍
- Runs Flake8 code style validation
- Calculates lint score (must be ≥7.5/10)
- Ensures code quality standards

#### Stage 3: Security 🔒
- Runs Bandit security scan on Python code
- Performs npm security audit
- Generates security reports
- Identifies vulnerabilities

#### Stage 4: Test 🧪
- Runs full test suite with pytest
- Generates coverage reports (requires ≥75% coverage)
- Uploads coverage to Codecov
- Validates all tests pass

#### Stage 5: Deploy 🚀
- Creates deployment package
- Prepares artifacts for deployment
- Ready for production/staging deployment
- Only runs on `main` and `develop` branches

**Triggers:**
- Push to: `main`, `develop`, `feature/**`
- Pull requests to: `main`, `develop`
- Manual trigger via GitHub Actions UI

### Environment Variables
For production, set these environment variables:
```bash
SECRET_KEY=your-secret-key-here
JWT_EXP_DELTA_SECONDS=3600
FLASK_DEBUG=False
```

## 📊 API Documentation

### POST /api/register
Register a new user.

**Request:**
```json
{
  "college_id": "PES123456",
  "name": "John Doe",
  "email": "john@pesu.edu",
  "password": "SecurePass123!",
  "role": "student"
}
```

**Response (201):**
```json
{
  "message": "Success: User registration complete. Redirecting to login page.",
  "success": true
}
```

### POST /api/login
Authenticate and get JWT token.

**Request:**
```json
{
  "college_id": "PES123456",
  "password": "SecurePass123!"
}
```

**Response (200):**
```json
{
  "token": "eyJhbGc...",
  "success": true,
  "role": "student",
  "name": "John Doe"
}
```

### GET /api/me
Get current user information (requires Bearer token).

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "college_id": "PES123456",
  "role": "student",
  "name": "John Doe"
}
```

## 🤝 Contributing

1. Create a feature branch: `git checkout -b feature/feature-name`
2. Commit changes: `git commit -am 'Add feature'`
3. Push to branch: `git push origin feature/feature-name`
4. Create Pull Request to `develop` branch

Please ensure:
- All tests pass: `pytest tests/`
- Code is linted: `flake8 app.py tests/`
- Coverage doesn't decrease
- New features include tests

## 📝 Development Guidelines

### Branching Strategy
- `main`: Production-ready code
- `develop`: Development branch
- `feature/*`: Feature branches
- `bugfix/*`: Bug fix branches

### Commit Messages
Follow conventional commit format:
- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `style:` Code style changes
- `refactor:` Code refactoring
- `test:` Test-related changes

Example:
```
feat: Add lab reservation endpoint
fix: Correct password validation regex
docs: Update API documentation
```

## 🐛 Known Issues & TODOs

- [ ] Lab reservation endpoints (in progress)
- [ ] Email notification system
- [ ] Calendar UI widget
- [ ] Admin panel for lab management
- [ ] Rate limiting and request throttling
- [ ] Database migration system

## 📄 License

This project is developed for educational purposes as part of the PES University UE23CS341A curriculum.

---

**Course:** UE23CS341A  
**Institution:** PES University  
**Academic Year:** 2025  
**Semester:** 5th Sem  
**Last Updated:** November 2025
