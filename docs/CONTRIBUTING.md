# Contributing to FailScope RTL

Thank you for your interest in contributing to FailScope RTL.

## 1. Development Setup

### Prerequisites
- Python 3.11 or newer
- Git

### Virtual Environment Setup
```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Verify Setup
```bash
failscope version
failscope doctor
```

---

## 2. Running Automated Tests

Run the full automated test suite:
```bash
pytest
```

Run specific test categories:
```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Regression tests only
pytest tests/regression/
```

---

## 3. Running the Benchmark

Execute the reproducible synthetic benchmark:
```bash
failscope benchmark --out benchmark_results/
failscope evaluate benchmark_results/
```

---

## 4. Contributing Guidelines

1. **No External Network Dependencies**: All core parsing, clustering, and reporting functionality must work completely offline without external APIs.
2. **Deterministic & Reproducible**: Never use unbounded non-deterministic algorithms without explicit random seeds.
3. **Strict HTML Escaping**: Any user or log string rendered into HTML reports must be escaped using `html.escape()` to prevent XSS vulnerabilities.
4. **Honest Claims**: Never fabricate benchmark results, simulator availability, or root-cause guarantees.
5. **Preserve User Files**: Tests and CLI runs must never modify or overwrite user source files.
