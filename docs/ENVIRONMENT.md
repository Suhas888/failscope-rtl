# FailScope RTL -- Environment & Toolchain Record

This document records the exact development environment, discovered tools, and simulator availability for FailScope RTL.

## 1. Operating System & Host Environment
- **OS**: Microsoft Windows 11
- **Architecture**: AMD64 (x86_64)
- **Shell**: PowerShell 7 / Windows PowerShell
- **Terminal Encoding Considerations**: Console output uses ASCII-safe indicators (`[OK]`, `[FAIL]`, `[-]`) to guarantee compatibility across diverse Windows code pages (such as CP1252) without `UnicodeEncodeError`.

## 2. Python Runtime & Virtual Environment
- **Python Version**: Python 3.14.7 (Active in `.venv`)
- **Virtual Environment Path**: `.venv/` (project-local dedicated virtual environment)
- **Build Backend**: `setuptools.build_meta` (PEP 517 standard)
- **Package Installation**: Editable install via `pip install -e .`

### Key Installed Dependencies
- `scikit-learn`: 1.9.1 (used for TF-IDF vectorization, cosine similarity, agglomerative clustering, and evaluation metrics)
- `numpy`: 2.5.4 (used for distance matrix manipulations and vector features)
- `scipy`: 1.18.1 (transitive dependency of scikit-learn)
- `pytest`: 9.1.1 (automated test framework)
- `pytest-cov`: 7.1.0 (coverage measurement)

## 3. EDA Simulators Inspection
As verified by `failscope doctor`:
- `verilator`: **Not installed** on system PATH (`PATH` checked via `shutil.which('verilator')`).
- `iverilog`: **Not installed** on system PATH.
- `vcs`: **Not installed** on system PATH.

### Operational Implication & Fallback
The product objective requires FailScope RTL to remain 100% useful when no EDA simulator is installed.
- **Log Ingestion & Parsing**: Operates offline on pre-existing log files and JUnit XML files without needing simulator binaries.
- **Benchmark Execution**: All 120 benchmark scenarios are generated synthetically using Python templates with deterministic seeds. No EDA simulation runs are required.
- **Simulator-based mutations**: Documented as not executed due to missing simulator binaries on the host, adhering strictly to the honesty principle (never fabricating simulator runs).

## 4. Network & Cloud Services
- **Outbound Network Calls**: Zero. No network requests are made during parsing, clustering, benchmark execution, or reporting.
- **Authentication**: No API keys, cloud tokens, or accounts are required or collected.
