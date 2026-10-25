# Contributing to FailScope RTL

Thank you for your interest in contributing to FailScope RTL.

FailScope RTL is an experimental, local-first tool designed to help FPGA developers and RTL verification engineers triage simulation failures. We welcome community feedback, reproducible bug reports, and parser improvements.

---

## 1. Development Setup

### Prerequisites
- Python 3.11 or newer (Python 3.14 compatible)
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

Run test suite with coverage report:
```bash
pytest --cov=failscope --cov-report=term-missing
```

---

## 3. Reproducing a Sample

You can test the tool on the bundled synthetic/toy example logs without needing an EDA simulator:

```bash
# 1. Parse a Verilator error log
failscope parse examples/logs/verilator_example.log

# 2. Analyze a UVM log and generate an HTML report
failscope analyze examples/logs/uvm_example.log --out demo_report.html

# 3. Compare two simulation runs
failscope compare examples/logs/uvm_example.log examples/logs/uvm_example.log --out demo_diff.html
```

---

## 4. Reporting a Bug or Providing Feedback

When submitting bug reports or feedback:
1. Review [docs/FEEDBACK.md](docs/FEEDBACK.md) for the structured issue template.
2. Provide your exact tool version (`failscope version`) and sanitized failure excerpts.
3. **IMPORTANT - Privacy Warning**: Never upload proprietary RTL source code, confidential logs, internal company paths, or credentials. Always sanitize signal names and proprietary paths into generic placeholders (e.g., `counter.v`, `tb_top`, `0xDEAD`).

---

## 5. Contribution & Quality Standards

1. **No External Network Dependencies**: All core parsing, clustering, and reporting functionality must work completely offline without external APIs or cloud calls.
2. **Deterministic & Reproducible**: Never use unbounded non-deterministic algorithms without explicit random seeds. Keep Baseline 1 (B1) signature normalization as the default clustering mechanism.
3. **Strict HTML Escaping**: Any log string, test name, or metadata rendered into HTML reports must be escaped using `html.escape()` to prevent XSS vulnerabilities.
4. **Honest Claims**: Never fabricate benchmark results, simulator availability, or root-cause guarantees. Passing test suites must never be presented as proof of real-world commercial effectiveness.
5. **Preserve User Files**: Tests and CLI runs must operate non-destructively and never modify or overwrite user source files.
