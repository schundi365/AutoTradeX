# Security Scanning and QA Guide for APEX Trading Bot

## Overview

This guide provides comprehensive instructions for implementing security scanning, vulnerability detection, and quality assurance processes for the APEX trading bot. It covers automated scanning tools, manual review processes, and best practices for maintaining code quality and security.

## Table of Contents

1. [Code Vulnerability Scanning](#code-vulnerability-scanning)
2. [Dependency Security](#dependency-security)
3. [Static Application Security Testing (SAST)](#static-application-security-testing)
4. [Dynamic Application Security Testing (DAST)](#dynamic-application-security-testing)
5. [QA Process and Guidelines](#qa-process-and-guidelines)
6. [Code Review Checklist](#code-review-checklist)
7. [Testing Strategy](#testing-strategy)
8. [CI/CD Integration](#cicd-integration)

---

## Code Vulnerability Scanning

### 1. Python Security Scanning with Bandit

Bandit is a tool designed to find common security issues in Python code.

**Installation**:
```bash
pip install bandit
```

**Basic Usage**:
```bash
# Scan entire project
bandit -r . -f json -o bandit-report.json

# Scan specific directories
bandit -r core/ agents/ api/ -f html -o security-report.html

# Scan with severity filter (only high and medium)
bandit -r . -ll -f screen
```

**Configuration** (`.bandit`):
```yaml
exclude_dirs:
  - /tests/
  - /.venv/
  - /__pycache__/

tests:
  - B101  # assert_used
  - B601  # paramiko_calls

skips:
  - B311  # random (acceptable for non-crypto use)
```

**Common Issues Detected**:
- SQL injection vulnerabilities
- Hardcoded passwords or API keys
- Use of insecure functions (eval, exec, pickle)
- Weak cryptographic algorithms
- Path traversal vulnerabilities
- Command injection risks

**Example Output**:
```
>> Issue: [B105:hardcoded_password_string] Possible hardcoded password: 'my_secret_key'
   Severity: Low   Confidence: Medium
   Location: core/config.py:15
```

### 2. Safety - Dependency Vulnerability Scanner

Safety checks your installed dependencies for known security vulnerabilities.

**Installation**:
```bash
pip install safety
```

**Usage**:
```bash
# Check current environment
safety check

# Check requirements file
safety check -r requirements.txt

# Generate JSON report
safety check --json --output safety-report.json

# Check with full report
safety check --full-report
```

**Example Output**:
```
+==============================================================================+
| REPORT                                                                        |
+============================+===========+==========================+==========+
| package                    | installed | affected                 | ID       |
+============================+===========+==========================+==========+
| django                     | 2.2.0     | <2.2.28                  | 51457    |
+==============================================================================+
```

### 3. Pip-audit - Official PyPA Tool

Pip-audit is the official Python Packaging Authority tool for auditing Python packages.

**Installation**:
```bash
pip install pip-audit
```

**Usage**:
```bash
# Audit installed packages
pip-audit

# Audit requirements file
pip-audit -r requirements.txt

# Generate JSON report
pip-audit --format json --output audit-report.json

# Fix vulnerabilities automatically
pip-audit --fix
```

---

## Dependency Security

### 1. Dependabot (GitHub)

Dependabot automatically creates pull requests to update dependencies with security vulnerabilities.

**Setup** (`.github/dependabot.yml`):
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    reviewers:
      - "your-team"
    labels:
      - "dependencies"
      - "security"
```

**Features**:
- Automatic security updates
- Version compatibility checking
- Grouped updates for related packages
- Configurable update schedule

### 2. Snyk - Comprehensive Security Platform

Snyk provides vulnerability scanning, license compliance, and fix recommendations.

**Installation**:
```bash
npm install -g snyk
snyk auth
```

**Usage**:
```bash
# Test for vulnerabilities
snyk test

# Monitor project continuously
snyk monitor

# Test and fix
snyk test --json | snyk-to-html -o snyk-report.html

# Test Docker images
snyk container test python:3.11
```

**GitHub Integration**:
- Install Snyk GitHub App
- Automatic PR checks for vulnerabilities
- Fix PRs generated automatically
- Dashboard for vulnerability tracking

### 3. Requirements Pinning

Always pin dependencies to specific versions to prevent supply chain attacks.

**requirements.txt**:
```txt
# Good - pinned versions
fastapi==0.109.0
uvicorn==0.27.0
pandas==2.1.4

# Bad - unpinned versions
fastapi
uvicorn>=0.20.0
pandas~=2.0
```

**Generate pinned requirements**:
```bash
pip freeze > requirements-lock.txt
```

---

## Static Application Security Testing (SAST)

### 1. Semgrep - Fast Static Analysis

Semgrep finds bugs and enforces code standards using pattern matching.

**Installation**:
```bash
pip install semgrep
```

**Usage**:
```bash
# Run with default rules
semgrep --config=auto .

# Run specific rulesets
semgrep --config=p/python --config=p/security-audit .

# Generate JSON report
semgrep --config=auto --json --output=semgrep-report.json .

# CI mode (fail on findings)
semgrep --config=auto --error .
```

**Custom Rules** (`.semgrep.yml`):
```yaml
rules:
  - id: hardcoded-api-key
    pattern: |
      api_key = "..."
    message: "Hardcoded API key detected"
    severity: ERROR
    languages: [python]
  
  - id: sql-injection
    pattern: |
      cursor.execute(f"SELECT * FROM {$TABLE}")
    message: "Possible SQL injection"
    severity: WARNING
    languages: [python]
```

### 2. Pylint - Code Quality and Security

Pylint checks for errors, enforces coding standards, and detects security issues.

**Installation**:
```bash
pip install pylint
```

**Usage**:
```bash
# Scan entire project
pylint core/ agents/ api/

# Generate report
pylint core/ --output-format=json > pylint-report.json

# Check specific file
pylint core/data_lake.py
```

**Configuration** (`.pylintrc`):
```ini
[MASTER]
ignore=tests,.venv,__pycache__

[MESSAGES CONTROL]
disable=C0111,C0103,R0913

[FORMAT]
max-line-length=120

[DESIGN]
max-args=7
max-locals=20
```

### 3. MyPy - Type Checking

Type checking prevents many runtime errors and improves code quality.

**Installation**:
```bash
pip install mypy
```

**Usage**:
```bash
# Check entire project
mypy core/ agents/ api/

# Strict mode
mypy --strict core/

# Generate report
mypy core/ --html-report mypy-report/
```

**Configuration** (`mypy.ini`):
```ini
[mypy]
python_version = 3.11
warn_return_any = True
warn_unused_configs = True
disallow_untyped_defs = True
ignore_missing_imports = True

[mypy-tests.*]
ignore_errors = True
```

---

## Dynamic Application Security Testing (DAST)

### 1. OWASP ZAP - API Security Testing

OWASP ZAP tests running applications for vulnerabilities.

**Installation**:
```bash
docker pull owasp/zap2docker-stable
```

**Usage**:
```bash
# Baseline scan
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t http://localhost:8000 \
  -r zap-report.html

# Full scan
docker run -t owasp/zap2docker-stable zap-full-scan.py \
  -t http://localhost:8000 \
  -r zap-full-report.html

# API scan with OpenAPI spec
docker run -t owasp/zap2docker-stable zap-api-scan.py \
  -t http://localhost:8000/openapi.json \
  -f openapi \
  -r zap-api-report.html
```

### 2. API Fuzzing

Test API endpoints with malformed inputs to find vulnerabilities.

**Using Hypothesis**:
```python
from hypothesis import given, strategies as st
import requests

@given(
    symbol=st.text(min_size=1, max_size=100),
    limit=st.integers()
)
def test_api_fuzzing_ohlcv(symbol, limit):
    """Fuzz test OHLCV endpoint"""
    response = requests.get(
        f"http://localhost:8000/api/v1/market/ohlcv/{symbol}",
        params={"limit": limit}
    )
    # Should not crash, should return valid HTTP status
    assert response.status_code in [200, 400, 404, 422]
```

---

## QA Process and Guidelines

### 1. Code Review Process

**Pre-Review Checklist** (Author):
- [ ] All tests pass locally
- [ ] Code follows style guide (PEP 8)
- [ ] Type hints added for all functions
- [ ] Docstrings added for public APIs
- [ ] No hardcoded secrets or credentials
- [ ] Performance impact assessed
- [ ] Security implications considered

**Review Checklist** (Reviewer):
- [ ] Code is readable and maintainable
- [ ] Logic is correct and handles edge cases
- [ ] Error handling is appropriate
- [ ] Tests cover critical paths
- [ ] No security vulnerabilities introduced
- [ ] Performance is acceptable
- [ ] Documentation is clear

**Review Severity Levels**:
- **Blocker**: Must fix before merge (security issues, critical bugs)
- **Major**: Should fix before merge (logic errors, missing tests)
- **Minor**: Can fix after merge (style issues, minor improvements)
- **Nit**: Optional improvements (suggestions, preferences)

### 2. Pull Request Template

Create `.github/pull_request_template.md`:
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests added/updated
- [ ] Property tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Security
- [ ] No hardcoded secrets
- [ ] Input validation added
- [ ] Security scan passed (Bandit, Safety)
- [ ] Dependencies reviewed

## Performance
- [ ] Performance impact assessed
- [ ] Load testing performed (if applicable)
- [ ] No performance regressions

## Checklist
- [ ] Code follows style guide
- [ ] Type hints added
- [ ] Docstrings added
- [ ] Tests pass locally
- [ ] Documentation updated
```

### 3. Testing Guidelines

**Unit Test Requirements**:
- Minimum 85% code coverage
- Test happy path and edge cases
- Test error conditions
- Use descriptive test names
- Follow AAA pattern (Arrange, Act, Assert)

**Property Test Requirements**:
- Minimum 100 iterations per property
- Use fixed seed for reproducibility
- Tag with feature name and property number
- Test universal properties, not specific examples

**Integration Test Requirements**:
- Test component interactions
- Use Docker for isolated environment
- Mock external dependencies
- Test error recovery scenarios

**Example Test Structure**:
```python
# tests/unit/test_tick_collector.py
import pytest
from core.tick_collector import TickDataCollector

class TestTickDataCollector:
    @pytest.fixture
    def collector(self):
        return TickDataCollector()
    
    def test_store_tick_success(self, collector):
        """Test successful tick storage"""
        # Arrange
        tick = Tick(symbol="XAUUSD", bid=2050.0, ask=2050.5)
        
        # Act
        collector.store_tick(tick)
        
        # Assert
        retrieved = collector.get_tick(tick.timestamp)
        assert retrieved.bid == 2050.0
    
    def test_store_tick_invalid_data(self, collector):
        """Test tick storage with invalid data"""
        # Arrange
        tick = Tick(symbol="", bid=-1.0, ask=-1.0)
        
        # Act & Assert
        with pytest.raises(ValueError):
            collector.store_tick(tick)
```

### 4. Performance Benchmarking

**Benchmark Requirements**:
- Tick data capture: <100ms
- Indicator computation: <50ms
- Model inference: <20ms
- API response time: <200ms
- Dashboard update latency: <500ms

**Benchmarking Tool** (`pytest-benchmark`):
```bash
pip install pytest-benchmark
```

**Example Benchmark**:
```python
def test_indicator_computation_performance(benchmark):
    """Benchmark indicator computation time"""
    result = benchmark(compute_indicators, "XAUUSD", ohlcv_data)
    assert result is not None
    # pytest-benchmark will report timing statistics
```

---

## CI/CD Integration

### GitHub Actions Workflow

Create `.github/workflows/ci.yml`:

```yaml
name: CI Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install flake8 mypy bandit
          pip install -r requirements.txt
      
      - name: Run flake8
        run: flake8 core/ agents/ api/ --max-line-length=120
      
      - name: Run mypy
        run: mypy core/ agents/ api/ --ignore-missing-imports
      
      - name: Run Bandit security scan
        run: bandit -r core/ agents/ api/ -f json -o bandit-report.json
      
      - name: Upload Bandit report
        uses: actions/upload-artifact@v3
        with:
          name: bandit-report
          path: bandit-report.json

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install safety pip-audit
      
      - name: Run Safety check
        run: safety check --json --output safety-report.json
        continue-on-error: true
      
      - name: Run pip-audit
        run: pip-audit -r requirements.txt --format json --output audit-report.json
        continue-on-error: true
      
      - name: Upload security reports
        uses: actions/upload-artifact@v3
        with:
          name: security-reports
          path: |
            safety-report.json
            audit-report.json

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install pytest pytest-cov pytest-asyncio hypothesis
          pip install -r requirements.txt
      
      - name: Run unit tests
        run: pytest tests/unit/ -v --cov=core --cov=agents --cov=api --cov-report=xml --cov-report=html
      
      - name: Check coverage threshold
        run: |
          coverage report --fail-under=85
      
      - name: Run property tests
        run: pytest tests/properties/ -v --hypothesis-seed=12345
      
      - name: Upload coverage reports
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb:latest-pg15
        env:
          POSTGRES_PASSWORD: test_password
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install pytest pytest-asyncio
          pip install -r requirements.txt
      
      - name: Run integration tests
        run: pytest tests/integration/ -v
        env:
          TIMESCALE_URL: postgresql://postgres:test_password@localhost:5432/test
          REDIS_URL: redis://localhost:6379

  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install pytest pytest-benchmark
          pip install -r requirements.txt
      
      - name: Run performance tests
        run: pytest tests/performance/ -v --benchmark-only
      
      - name: Check for performance regressions
        run: |
          # Compare with baseline (fail if >10% regression)
          pytest tests/performance/ --benchmark-compare=baseline --benchmark-compare-fail=mean:10%
```

### Deployment Workflow

Create `.github/workflows/deploy.yml`:
```yaml
name: Deploy Pipeline

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy to staging
        run: |
          # Your deployment script
          ./scripts/deploy.sh staging
      
      - name: Run smoke tests
        run: |
          pytest tests/smoke/ --env=staging

  deploy-production:
    runs-on: ubuntu-latest
    needs: deploy-staging
    environment: production
    steps:
      - uses: actions/checkout@v3
      
      - name: Deploy canary (10% traffic)
        run: |
          ./scripts/deploy.sh production --canary=10
      
      - name: Monitor canary metrics
        run: |
          ./scripts/monitor_canary.sh --duration=300 --error-threshold=1
      
      - name: Full deployment
        if: success()
        run: |
          ./scripts/deploy.sh production --full
      
      - name: Rollback on failure
        if: failure()
        run: |
          ./scripts/rollback.sh production
```

---

## Secret Management

### 1. Environment Variables

Never commit secrets to version control. Use environment variables.

**Good Practice**:
```python
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TRADING_API_KEY")
DB_PASSWORD = os.getenv("DB_PASSWORD")

if not API_KEY:
    raise ValueError("TRADING_API_KEY environment variable not set")
```

**Bad Practice**:
```python
# DON'T DO THIS
API_KEY = "sk_live_abc123xyz"
DB_PASSWORD = "my_secret_password"
```

### 2. Git-secrets - Prevent Secret Commits

Git-secrets prevents committing secrets to repositories.

**Installation**:
```bash
# macOS
brew install git-secrets

# Linux
git clone https://github.com/awslabs/git-secrets
cd git-secrets
make install
```

**Setup**:
```bash
# Initialize in repository
cd /path/to/apex-bot
git secrets --install

# Add patterns to detect
git secrets --register-aws
git secrets --add 'api[_-]?key.*=.*["\'][a-zA-Z0-9]{20,}["\']'
git secrets --add 'password.*=.*["\'][^"\']{8,}["\']'

# Scan repository
git secrets --scan
```

### 3. Detect-secrets - Pre-commit Hook

Detect-secrets prevents secrets from being committed.

**Installation**:
```bash
pip install detect-secrets
```

**Setup**:
```bash
# Generate baseline
detect-secrets scan > .secrets.baseline

# Add to pre-commit hook
```

**Pre-commit Configuration** (`.pre-commit-config.yaml`):
```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

---

## Code Quality Standards

### 1. PEP 8 Style Guide

Follow Python's official style guide.

**Key Rules**:
- Indentation: 4 spaces
- Line length: 120 characters (configurable)
- Naming: snake_case for functions/variables, PascalCase for classes
- Imports: Standard library → Third-party → Local
- Docstrings: Use for all public functions and classes

**Automated Formatting**:
```bash
# Install formatters
pip install black isort

# Format code
black core/ agents/ api/
isort core/ agents/ api/

# Check without modifying
black --check core/
isort --check-only core/
```

### 2. Documentation Standards

**Docstring Format** (Google Style):
```python
def compute_indicators(symbol: str, ohlcv_data: List[dict]) -> Dict[str, float]:
    """
    Compute technical indicators for a symbol.
    
    Args:
        symbol: Trading symbol (e.g., "XAUUSD")
        ohlcv_data: List of OHLCV dictionaries with keys: open, high, low, close, volume
    
    Returns:
        Dictionary mapping indicator names to values
    
    Raises:
        ValueError: If ohlcv_data is empty or missing required columns
    
    Example:
        >>> indicators = compute_indicators("XAUUSD", ohlcv_data)
        >>> print(indicators["rsi"])
        65.3
    """
    pass
```

### 3. Error Handling Standards

**Always**:
- Use specific exception types
- Log errors with context
- Provide meaningful error messages
- Clean up resources in finally blocks

**Example**:
```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def fetch_market_data(symbol: str) -> Optional[dict]:
    """Fetch market data with proper error handling"""
    try:
        response = await api_client.get(f"/market/{symbol}")
        response.raise_for_status()
        return response.json()
    
    except aiohttp.ClientTimeout:
        logger.error(f"Timeout fetching data for {symbol}")
        return None
    
    except aiohttp.ClientError as e:
        logger.error(f"API error for {symbol}: {e}")
        return None
    
    except Exception as e:
        logger.exception(f"Unexpected error fetching {symbol}: {e}")
        return None
```

---

## Testing Strategy

### 1. Test Pyramid

```
        /\
       /  \
      / E2E \
     /______\
    /        \
   /Integration\
  /____________\
 /              \
/   Unit Tests   \
/________________\
```

**Distribution**:
- Unit tests: 70% (fast, isolated, many)
- Integration tests: 20% (moderate speed, component interactions)
- End-to-end tests: 10% (slow, full system, few)

### 2. Test Organization

```
tests/
├── unit/
│   ├── test_tick_collector.py
│   ├── test_sentiment_analyzer.py
│   ├── test_feature_pipeline.py
│   └── ...
├── properties/
│   ├── test_tick_data_properties.py
│   ├── test_order_book_properties.py
│   ├── test_ml_model_properties.py
│   └── ...
├── integration/
│   ├── test_data_flow.py
│   ├── test_ml_pipeline.py
│   └── test_dashboard_updates.py
├── performance/
│   ├── test_tick_collection_perf.py
│   ├── test_indicator_computation_perf.py
│   └── test_model_inference_perf.py
└── conftest.py  # Shared fixtures
```

### 3. Test Fixtures

**Shared Fixtures** (`tests/conftest.py`):
```python
import pytest
from datetime import datetime

@pytest.fixture
def sample_tick():
    """Sample tick data for testing"""
    return Tick(
        symbol="XAUUSD",
        timestamp=datetime.now(),
        bid=2050.0,
        ask=2050.5,
        last=2050.25,
        volume=100
    )

@pytest.fixture
def sample_ohlcv():
    """Sample OHLCV data for testing"""
    return [
        {"open": 2050, "high": 2055, "low": 2048, "close": 2053, "volume": 1000}
        for _ in range(100)
    ]

@pytest.fixture
async def event_bus():
    """Event bus for testing"""
    bus = EventBus()
    yield bus
    await bus.shutdown()
```

---

## Security Best Practices

### 1. Input Validation

Always validate and sanitize user inputs.

**Example**:
```python
from pydantic import BaseModel, validator, Field

class OHLCVRequest(BaseModel):
    symbol: str = Field(..., regex="^[A-Z]{6,10}$")
    limit: int = Field(default=100, ge=1, le=5000)
    
    @validator('symbol')
    def validate_symbol(cls, v):
        allowed_symbols = ["XAUUSD", "EURUSD", "BTCUSD"]
        if v not in allowed_symbols:
            raise ValueError(f"Invalid symbol: {v}")
        return v
```

### 2. SQL Injection Prevention

Use parameterized queries, never string formatting.

**Good**:
```python
# Using parameterized query
cursor.execute(
    "SELECT * FROM trades WHERE symbol = ? AND date > ?",
    (symbol, start_date)
)
```

**Bad**:
```python
# DON'T DO THIS - SQL injection risk
cursor.execute(f"SELECT * FROM trades WHERE symbol = '{symbol}'")
```

### 3. API Security

**Rate Limiting**:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.get("/api/v1/market/ohlcv/{symbol}")
@limiter.limit("100/minute")
async def get_ohlcv(symbol: str, request: Request):
    pass
```

**Authentication** (if needed):
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if not is_valid_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )
    return token
```

### 4. Secure Configuration

**Use environment-specific configs**:
```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    # Database
    db_host: str
    db_password: str
    
    # API Keys
    trading_api_key: str
    news_api_key: str
    
    # Security
    secret_key: str
    allowed_origins: List[str] = ["http://localhost:3000"]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

**.env.example** (commit this):
```bash
DB_HOST=localhost
DB_PASSWORD=your_password_here
TRADING_API_KEY=your_api_key_here
NEWS_API_KEY=your_news_api_key_here
SECRET_KEY=your_secret_key_here
```

**.env** (never commit this):
```bash
DB_HOST=production-db.example.com
DB_PASSWORD=actual_secure_password
TRADING_API_KEY=sk_live_abc123xyz
NEWS_API_KEY=news_api_key_xyz
SECRET_KEY=super_secret_key_123
```

---

## Vulnerability Scanning Schedule

### Daily Scans (Automated)
- Dependency vulnerability scanning (Safety, pip-audit)
- SAST scanning (Bandit)
- Code quality checks (Pylint, MyPy)

### Weekly Scans (Automated)
- Full security audit (Snyk)
- Dependency updates (Dependabot PRs)
- Performance regression tests

### Monthly Scans (Manual)
- DAST scanning (OWASP ZAP)
- Penetration testing (if applicable)
- Security audit review
- Update security policies

---

## QA Checklist for Feature Development

### Before Starting Development
- [ ] Requirements documented and reviewed
- [ ] Design document created and approved
- [ ] Security implications assessed
- [ ] Performance requirements defined
- [ ] Test strategy planned

### During Development
- [ ] Write tests alongside code (TDD)
- [ ] Run tests locally before committing
- [ ] Follow code style guide
- [ ] Add type hints and docstrings
- [ ] Handle errors gracefully
- [ ] Log important events
- [ ] No hardcoded secrets

### Before Creating PR
- [ ] All tests pass locally
- [ ] Code coverage ≥85%
- [ ] Security scan passed (Bandit)
- [ ] Dependency scan passed (Safety)
- [ ] Code formatted (Black, isort)
- [ ] Type checking passed (MyPy)
- [ ] Documentation updated
- [ ] Performance benchmarks met

### During Code Review
- [ ] Logic is correct
- [ ] Tests are comprehensive
- [ ] Error handling is appropriate
- [ ] Security vulnerabilities addressed
- [ ] Performance is acceptable
- [ ] Code is maintainable

### Before Merging
- [ ] All review comments addressed
- [ ] CI pipeline passed
- [ ] At least 1 approval from team member
- [ ] No merge conflicts
- [ ] Branch is up to date with main

### After Merging
- [ ] Monitor deployment
- [ ] Check error logs
- [ ] Verify metrics
- [ ] Update documentation if needed

---

## Common Vulnerabilities to Watch For

### 1. Injection Attacks
- SQL injection in database queries
- Command injection in shell commands
- Code injection via eval/exec

**Prevention**:
- Use parameterized queries
- Avoid shell=True in subprocess
- Never use eval/exec on user input

### 2. Authentication and Authorization
- Weak password policies
- Missing authentication on sensitive endpoints
- Insufficient authorization checks

**Prevention**:
- Use strong authentication (OAuth2, JWT)
- Implement role-based access control
- Validate permissions on every request

### 3. Sensitive Data Exposure
- Hardcoded credentials
- Logging sensitive information
- Exposing internal errors to users

**Prevention**:
- Use environment variables for secrets
- Sanitize logs (remove PII, credentials)
- Return generic error messages to users

### 4. Insecure Dependencies
- Using packages with known vulnerabilities
- Outdated dependencies
- Malicious packages

**Prevention**:
- Regular dependency updates
- Automated vulnerability scanning
- Review dependencies before adding

### 5. Insufficient Logging and Monitoring
- Missing security event logs
- No alerting on suspicious activity
- Insufficient audit trail

**Prevention**:
- Log all authentication attempts
- Log all data access and modifications
- Set up alerts for anomalies
- Maintain audit trail for compliance

---

## Tools Summary

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **Bandit** | Python SAST | Every commit (CI) |
| **Safety** | Dependency vulnerabilities | Daily (CI) |
| **Pip-audit** | Official PyPA auditing | Daily (CI) |
| **Snyk** | Comprehensive security | Weekly (CI + monitoring) |
| **Dependabot** | Automated dependency updates | Continuous (GitHub) |
| **Semgrep** | Custom security rules | Every commit (CI) |
| **Pylint** | Code quality | Every commit (CI) |
| **MyPy** | Type checking | Every commit (CI) |
| **OWASP ZAP** | DAST for APIs | Weekly (manual) |
| **Git-secrets** | Prevent secret commits | Pre-commit hook |
| **Detect-secrets** | Secret detection | Pre-commit hook |

---

## Quick Start Commands

### Run All Security Scans Locally
```bash
# Install tools
pip install bandit safety pip-audit pylint mypy

# Run scans
bandit -r core/ agents/ api/ -f screen
safety check
pip-audit -r requirements.txt
pylint core/ agents/ api/
mypy core/ agents/ api/
```

### Run All Tests Locally
```bash
# Install test dependencies
pip install pytest pytest-cov pytest-asyncio hypothesis pytest-benchmark

# Run all tests with coverage
pytest tests/ -v --cov=core --cov=agents --cov=api --cov-report=html

# Run only property tests
pytest tests/properties/ -v --hypothesis-seed=12345

# Run performance benchmarks
pytest tests/performance/ --benchmark-only
```

### Format Code
```bash
# Install formatters
pip install black isort

# Format all code
black core/ agents/ api/ tests/
isort core/ agents/ api/ tests/

# Check formatting
black --check core/
isort --check-only core/
```

---

## Continuous Improvement

### Monthly Security Review
1. Review all security scan results
2. Update dependencies to latest secure versions
3. Review and update security policies
4. Conduct threat modeling for new features
5. Update this guide with new findings

### Quarterly Security Audit
1. External security audit (if budget allows)
2. Penetration testing
3. Review access controls and permissions
4. Update incident response plan
5. Security training for team

---

## Resources

### Documentation
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [Safety Documentation](https://pyup.io/safety/)

### Tools
- [Snyk](https://snyk.io/)
- [Dependabot](https://github.com/dependabot)
- [OWASP ZAP](https://www.zaproxy.org/)
- [Semgrep](https://semgrep.dev/)

### Training
- [OWASP Security Knowledge Framework](https://www.securityknowledgeframework.org/)
- [Python Security Course](https://www.pluralsight.com/courses/python-security)
