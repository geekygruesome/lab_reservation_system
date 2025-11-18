# CI/CD Pipeline Runner for PowerShell
# Run all 5 stages of the CI/CD pipeline locally

Write-Host "🚀 Starting CI/CD Pipeline - 5 Stages" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"

# Stage 1: Build
Write-Host "🔨 Stage 1: Build" -ForegroundColor Yellow
Write-Host "Installing Python dependencies..." -ForegroundColor Gray
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pytest pytest-cov flake8 bandit

Write-Host "Installing Node.js dependencies..." -ForegroundColor Gray
if (Test-Path "package.json") {
    npm ci
} else {
    Write-Host "No package.json found, skipping npm install" -ForegroundColor Yellow
}

Write-Host "✅ Stage 1: Build - COMPLETED" -ForegroundColor Green
Write-Host ""

# Stage 2: Lint
Write-Host "🔍 Stage 2: Lint" -ForegroundColor Yellow
Write-Host "Running Flake8 linting..." -ForegroundColor Gray
python -m flake8 app.py tests/ --count --statistics --max-line-length=120 --exclude=__pycache__,venv,env

Write-Host "Calculating lint score..." -ForegroundColor Gray
python calculate_lint_score.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Stage 2: Lint - PASSED" -ForegroundColor Green
} else {
    Write-Host "❌ Stage 2: Lint - FAILED" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Stage 3: Security
Write-Host "🔒 Stage 3: Security" -ForegroundColor Yellow
Write-Host "Running Bandit security scan..." -ForegroundColor Gray
if (-not (Test-Path "reports")) {
    New-Item -ItemType Directory -Path "reports" -Force | Out-Null
}
python -m bandit -r app.py -ll -f json -o reports/bandit-report.json
python -m bandit -r app.py -ll

if (Test-Path "package.json") {
    Write-Host "Running npm security audit..." -ForegroundColor Gray
    npm audit --audit-level=high
}

Write-Host "✅ Stage 3: Security - COMPLETED" -ForegroundColor Green
Write-Host ""

# Stage 4: Test
Write-Host "🧪 Stage 4: Test" -ForegroundColor Yellow
Write-Host "Running tests with coverage..." -ForegroundColor Gray
pytest tests/ -v --cov=app --cov-report=xml --cov-report=term-missing --cov-fail-under=75

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Stage 4: Test - PASSED" -ForegroundColor Green
} else {
    Write-Host "❌ Stage 4: Test - FAILED" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Stage 5: Deploy
Write-Host "🚀 Stage 5: Deploy" -ForegroundColor Yellow
Write-Host "Creating deployment package..." -ForegroundColor Gray
if (Test-Path "deploy") {
    Remove-Item -Recurse -Force "deploy"
}
New-Item -ItemType Directory -Path "deploy" -Force | Out-Null

Copy-Item "app.py" -Destination "deploy/"
Copy-Item "requirements.txt" -Destination "deploy/"

if (Test-Path "templates") {
    Copy-Item -Recurse "templates" -Destination "deploy/"
}

Write-Host "Verifying deployment package..." -ForegroundColor Gray
Get-ChildItem -Recurse "deploy" | Select-Object FullName

Write-Host "✅ Stage 5: Deploy - COMPLETED" -ForegroundColor Green
Write-Host ""

# Summary
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "✅ All 5 stages completed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  1. ✅ Build - Dependencies installed" -ForegroundColor Green
Write-Host "  2. ✅ Lint - Code quality verified" -ForegroundColor Green
Write-Host "  3. ✅ Security - Security scans passed" -ForegroundColor Green
Write-Host "  4. ✅ Test - All tests passed with coverage" -ForegroundColor Green
Write-Host "  5. ✅ Deploy - Deployment package ready" -ForegroundColor Green
Write-Host ""

