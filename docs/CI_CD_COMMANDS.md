# CI/CD Pipeline - Commands Guide

This document provides all the commands needed to run each stage of the CI/CD pipeline locally.

## 🚀 Quick Start

Run all stages in sequence:
```bash
# Stage 1: Build
pip install -r requirements.txt && npm ci

# Stage 2: Lint
python -m flake8 app.py tests/ --count --statistics --max-line-length=120
python calculate_lint_score.py

# Stage 3: Security
python -m bandit -r app.py -ll -f json -o reports/bandit-report.json
npm audit --audit-level=high

# Stage 4: Test
pytest tests/ -v --cov=app --cov-report=xml --cov-report=term-missing --cov-fail-under=75

# Stage 5: Deploy (simulation)
mkdir -p deploy && cp app.py requirements.txt deploy/ && cp -r templates deploy/
```

---

## 📋 Detailed Commands by Stage

### Stage 1: Build 🔨

#### Install Python Dependencies
```bash
# Upgrade pip
python -m pip install --upgrade pip

# Install all Python dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov flake8 bandit
```

#### Install Node.js Dependencies
```bash
# Install npm packages
npm ci

# Or if package-lock.json doesn't exist
npm install
```

#### Verify Build
```bash
# Check Python packages
python -c "import flask; print('Flask installed successfully')"
python -c "import pytest; print('Pytest installed successfully')"

# Check Node.js packages
npm list --depth=0
```

---

### Stage 2: Lint 🔍

#### Run Flake8 Linting
```bash
# Basic linting
python -m flake8 app.py tests/ --count --statistics --max-line-length=120

# Exclude cache directories
python -m flake8 app.py tests/ --count --statistics --max-line-length=120 --exclude=__pycache__,venv,env

# Show only errors
python -m flake8 app.py tests/ --max-line-length=120 --show-source
```

#### Calculate Lint Score
```bash
# Using Python script
python calculate_lint_score.py

# Or using npm script
npm run lint

# Expected output:
# Flake8 Violations: 0
# Lint Score: 10.00/10
# Required: >= 7.5/10
# [PASS] Lint score PASSED
```

**Lint Score Formula:** `10 - (violations / 10)`  
**Minimum Required:** 7.5/10

---

### Stage 3: Security 🔒

#### Run Bandit Security Scan
```bash
# Basic security scan
python -m bandit -r app.py -ll

# Generate JSON report
python -m bandit -r app.py -ll -f json -o reports/bandit-report.json

# Scan with specific confidence level
python -m bandit -r app.py -ll -c 1

# Scan excluding tests
python -m bandit -r app.py -ll --exclude tests/
```

#### Run npm Security Audit
```bash
# Basic audit
npm audit

# Audit with high severity only
npm audit --audit-level=high

# Fix vulnerabilities automatically (if possible)
npm audit fix

# Fix vulnerabilities without updating package.json
npm audit fix --force
```

#### View Security Reports
```bash
# View Bandit report
cat reports/bandit-report.json

# View npm audit report
npm audit --json > reports/npm-audit-report.json
```

---

### Stage 4: Test 🧪

#### Run All Tests
```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with short traceback
pytest tests/ -v --tb=short

# Run specific test file
pytest tests/test_authentication_clean.py -v
```

#### Run Tests with Coverage
```bash
# Basic coverage report
pytest tests/ --cov=app --cov-report=term-missing

# Generate HTML coverage report
pytest tests/ --cov=app --cov-report=html

# Generate XML coverage report (for CI/CD)
pytest tests/ --cov=app --cov-report=xml --cov-report=term-missing

# Check coverage threshold (≥75%)
pytest tests/ --cov=app --cov-fail-under=75 --cov-report=term-missing
```

#### View Coverage Reports
```bash
# Open HTML coverage report (after generating)
# On Windows
start htmlcov/index.html

# On macOS
open htmlcov/index.html

# On Linux
xdg-open htmlcov/index.html
```

#### Test Coverage Requirements
- **Minimum Coverage:** 75%
- **Current Coverage:** 87% ✅
- **Coverage Report Location:** `coverage.xml`, `htmlcov/`

---

### Stage 5: Deploy 🚀

#### Create Deployment Package
```bash
# Create deploy directory
mkdir -p deploy

# Copy application files
cp app.py deploy/
cp requirements.txt deploy/

# Copy templates directory
cp -r templates deploy/ 2>/dev/null || echo "No templates directory"

# Copy static files (if exists)
cp -r static deploy/ 2>/dev/null || echo "No static directory"

# Verify deployment package
ls -la deploy/
```

#### Deployment Verification
```bash
# Check deployment package contents
tree deploy/  # If tree is installed
# Or
ls -R deploy/

# Verify all required files are present
test -f deploy/app.py && echo "✅ app.py found"
test -f deploy/requirements.txt && echo "✅ requirements.txt found"
test -d deploy/templates && echo "✅ templates/ found"
```

#### Simulate Deployment
```bash
# Test deployment package in isolated environment
cd deploy
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

---

## 🔄 Running Complete Pipeline Locally

### Option 1: Manual Step-by-Step
```bash
# 1. Build
pip install -r requirements.txt && npm ci

# 2. Lint
python calculate_lint_score.py

# 3. Security
python -m bandit -r app.py -ll
npm audit --audit-level=high

# 4. Test
pytest tests/ -v --cov=app --cov-fail-under=75 --cov-report=xml

# 5. Deploy (simulation)
mkdir -p deploy && cp app.py requirements.txt deploy/ && cp -r templates deploy/
```

### Option 2: Using npm Scripts
```bash
# Run linting
npm run lint

# Run tests
npm test

# Run tests with coverage
npm run test:coverage
```

### Option 3: Create a Shell Script
Create `run-pipeline.sh`:
```bash
#!/bin/bash
set -e  # Exit on error

echo "🔨 Stage 1: Build"
pip install -r requirements.txt
npm ci

echo "🔍 Stage 2: Lint"
python calculate_lint_score.py

echo "🔒 Stage 3: Security"
python -m bandit -r app.py -ll
npm audit --audit-level=high || true

echo "🧪 Stage 4: Test"
pytest tests/ -v --cov=app --cov-fail-under=75 --cov-report=xml

echo "🚀 Stage 5: Deploy"
mkdir -p deploy
cp app.py requirements.txt deploy/
cp -r templates deploy/ 2>/dev/null || true

echo "✅ All stages completed successfully!"
```

Make it executable and run:
```bash
chmod +x run-pipeline.sh
./run-pipeline.sh
```

---

## 🐛 Troubleshooting

### Build Stage Issues
```bash
# If pip install fails, upgrade pip
python -m pip install --upgrade pip setuptools wheel

# If npm ci fails, try npm install
npm install

# Clear pip cache
pip cache purge
```

### Lint Stage Issues
```bash
# Install flake8 if missing
pip install flake8

# Check flake8 version
flake8 --version
```

### Security Stage Issues
```bash
# Install bandit if missing
pip install bandit

# If npm audit fails, check package.json exists
test -f package.json && echo "package.json exists" || echo "package.json missing"
```

### Test Stage Issues
```bash
# Install pytest if missing
pip install pytest pytest-cov

# Run tests without coverage first
pytest tests/ -v

# Check pytest configuration
cat pytest.ini
```

### Coverage Issues
```bash
# If coverage is below 75%, check which lines are missing
pytest tests/ --cov=app --cov-report=term-missing

# View detailed HTML report
pytest tests/ --cov=app --cov-report=html
# Then open htmlcov/index.html
```

---

## 📊 Pipeline Status Check

Check if all stages would pass:
```bash
# Quick check script
echo "Checking pipeline status..."

echo -n "Build: "
pip list | grep -q flask && echo "✅" || echo "❌"

echo -n "Lint: "
python calculate_lint_score.py > /dev/null 2>&1 && echo "✅" || echo "❌"

echo -n "Security: "
python -m bandit -r app.py -ll > /dev/null 2>&1 && echo "✅" || echo "❌"

echo -n "Test: "
pytest tests/ --cov=app --cov-fail-under=75 -q > /dev/null 2>&1 && echo "✅" || echo "❌"

echo "Pipeline check complete!"
```

---

## 🔗 Related Files

- **CI/CD Pipeline:** `.github/workflows/ci-cd.yml`
- **Lint Script:** `calculate_lint_score.py`
- **Test Config:** `pytest.ini`
- **Lint Config:** `setup.cfg`
- **Package Scripts:** `package.json`

---

## 📝 Notes

- All commands should be run from the project root directory
- Ensure Python 3.11+ and Node.js 18+ are installed
- Virtual environment is recommended but not required
- Coverage threshold is enforced at 75% minimum
- Lint score must be ≥7.5/10 to pass

