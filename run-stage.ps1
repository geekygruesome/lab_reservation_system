# Run Individual CI/CD Pipeline Stages
# Usage: .\run-stage.ps1 <stage_number>
# Example: .\run-stage.ps1 1

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet(1,2,3,4,5)]
    [int]$Stage
)

$ErrorActionPreference = "Stop"

switch ($Stage) {
    1 {
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
    }
    
    2 {
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
    }
    
    3 {
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
    }
    
    4 {
        Write-Host "🧪 Stage 4: Test" -ForegroundColor Yellow
        Write-Host "Running tests with coverage..." -ForegroundColor Gray
        pytest tests/ -v --cov=app --cov-report=xml --cov-report=term-missing --cov-fail-under=75
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Stage 4: Test - PASSED" -ForegroundColor Green
        } else {
            Write-Host "❌ Stage 4: Test - FAILED" -ForegroundColor Red
            exit 1
        }
    }
    
    5 {
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
    }
}

