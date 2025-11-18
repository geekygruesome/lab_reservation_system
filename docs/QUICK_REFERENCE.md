# Quick Reference - CI/CD Pipeline Commands

## 🚀 Run All Stages (Quick)

### PowerShell (Windows)
```powershell
# Run all 5 stages at once
.\run-pipeline.ps1

# Or run individual stages
.\run-stage.ps1 1  # Build
.\run-stage.ps1 2  # Lint
.\run-stage.ps1 3  # Security
.\run-stage.ps1 4  # Test
.\run-stage.ps1 5  # Deploy
```

### Bash/Linux/Mac

```bash
# 1. Build
pip install -r requirements.txt && npm ci

# 2. Lint
python calculate_lint_score.py

# 3. Security  
python -m bandit -r app.py -ll && npm audit --audit-level=high

# 4. Test
pytest tests/ -v --cov=app --cov-fail-under=75

# 5. Deploy (simulation)
mkdir -p deploy && cp app.py requirements.txt deploy/ && cp -r templates deploy/
```

## 📋 Individual Stage Commands

### Stage 1: Build
```bash
pip install -r requirements.txt
npm ci
```

### Stage 2: Lint
```bash
python -m flake8 app.py tests/ --max-line-length=120
python calculate_lint_score.py
```

### Stage 3: Security
```bash
python -m bandit -r app.py -ll
npm audit --audit-level=high
```

### Stage 4: Test
```bash
pytest tests/ -v --cov=app --cov-fail-under=75
```

### Stage 5: Deploy
```bash
mkdir -p deploy
cp app.py requirements.txt deploy/
cp -r templates deploy/
```

## 📁 Pipeline File Location

- **Main Pipeline:** `.github/workflows/ci-cd.yml` (5 stages)
- **Old Pipeline:** `.github/workflows/ci.yml` (can be removed if not needed)

## ✅ Requirements

- **Lint Score:** ≥7.5/10
- **Test Coverage:** ≥75%
- **Python:** 3.11+
- **Node.js:** 18+

## 🔗 Full Documentation

See `docs/CI_CD_COMMANDS.md` for detailed commands and troubleshooting.

