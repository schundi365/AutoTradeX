#!/bin/bash
# Security scanning script for APEX Trading Bot

set -e

echo "=========================================="
echo "APEX Trading Bot - Security Scan"
echo "=========================================="
echo ""

# Check if tools are installed
echo "Checking for required tools..."
command -v bandit >/dev/null 2>&1 || { echo "Installing bandit..."; pip install bandit; }
command -v safety >/dev/null 2>&1 || { echo "Installing safety..."; pip install safety; }
command -v pip-audit >/dev/null 2>&1 || { echo "Installing pip-audit..."; pip install pip-audit; }

echo ""
echo "=========================================="
echo "1. Running Bandit (SAST for Python)"
echo "=========================================="
bandit -r core/ agents/ api/ -f screen -ll

echo ""
echo "=========================================="
echo "2. Running Safety (Dependency Vulnerabilities)"
echo "=========================================="
safety check --full-report || true

echo ""
echo "=========================================="
echo "3. Running pip-audit (PyPA Official Tool)"
echo "=========================================="
pip-audit || true

echo ""
echo "=========================================="
echo "Security scan complete!"
echo "=========================================="
echo ""
echo "Reports generated:"
echo "  - Bandit: See output above"
echo "  - Safety: See output above"
echo "  - pip-audit: See output above"
echo ""
echo "To generate JSON reports, run:"
echo "  bandit -r core/ agents/ api/ -f json -o reports/bandit-report.json"
echo "  safety check --json --output reports/safety-report.json"
echo "  pip-audit --format json --output reports/audit-report.json"
