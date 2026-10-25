# FailScope RTL

**Local-first RTL simulation regression failure investigator.**

FailScope RTL helps FPGA developers and RTL verification engineers turn repetitive simulation failures into an organised, evidence-backed report. It groups failure signatures, diffs regression runs to identify new versus resolved failures, and generates self-contained, offline HTML reports.

> [!IMPORTANT]
> **Project Status: Experimental Alpha Research Prototype**  
> FailScope RTL is an experimental research tool. It has not been validated on production tape-out regression suites, does not guarantee root-cause identification, and does not claim universal simulator compatibility. Passing the internal automated test suite demonstrates software correctness and algorithmic reproducibility, not commercial or real-world effectiveness.

---

## What Problem Does It Solve?

Running nightly regression suites across hundreds of tests often produces dozens or hundreds of failure messages. Most CI dashboards simply present an unaggregated list of failing test names. 

FailScope RTL:
1. **Aggregates Repetitive Failures**: Normalizes variable runtime noise (random seeds, simulation timestamps like `@ 1000ns`, and hex memory addresses like `0xDEADBEEF`) using deterministic regex signatures (Baseline 1 - B1, Default).
2. **Preserves Raw Evidence**: Attaches context lines and source locations (`counter.v:42`) to representative cluster cards.
3. **Diffs Consecutive Runs**: Compares two simulation runs to categorize failure signatures into `NEW_FAILURES`, `RESOLVED`, and `PERSISTENT`.
4. **100% Local & Offline**: Operates completely in-memory and on the local filesystem with zero outbound network calls, zero external CDNs, and zero telemetry.

---

## What It Does NOT Do

- **Does NOT fix RTL code**: It is an investigative log analyzer, not an automated RTL synthesis or repair tool.
- **Does NOT require or access RTL source files**: It inspects only output logs and XML test results.
- **Does NOT guarantee root cause**: Groups failure symptoms, not the originating hardware defect.
- **Does NOT include a simulator**: Requires logs produced by your existing simulation flows (Verilator, UVM, Cocotb, etc.).
- **Does NOT use cloud APIs**: Requires no paid subscriptions, accounts, or internet connectivity.

---

## Prerequisites

- **Python**: 3.11 or newer (tested on Python 3.11 through 3.14).
- **Operating System**: Linux, macOS, or Windows (PowerShell / Command Prompt).
- **Simulators**: No EDA simulator installation is required to run FailScope; it processes pre-existing log files and JUnit XML files.

---

## Installation

### Windows PowerShell
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### Linux / macOS
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Quick Start (Copy-Pasteable CLI Commands)

FailScope provides CLI commands for environment validation, parsing, full triage analysis, and run comparison:

### 1. Verify Environment (`doctor`)
```bash
failscope doctor
```
Checks installed Python packages and detects any installed EDA simulators on `PATH`.

### 2. Parse a Simulation Log (`parse`)
```bash
failscope parse examples/logs/verilator_example.log
```
Extracts failure records and prints extracted signatures and locations to the terminal.

### 3. Analyze and Generate HTML Report (`analyze`)
```bash
failscope analyze examples/logs/uvm_example.log --out report.html
```
Parses failures, clusters them using Baseline 1 (B1) signature normalization, and writes a self-contained HTML report. Open `report.html` in any browser.

### 4. Compare Two Regression Runs (`compare`)
```bash
failscope compare examples/logs/uvm_example.log examples/logs/uvm_example.log --out compare_report.html
```
Compares a baseline regression run against a candidate run, highlighting new failure signatures, resolved failures, and persistent issues.

---

## Reproducible Example

The repository includes handcrafted, synthetic toy example logs in [`examples/logs/`](examples/logs/):

### Input (`examples/logs/uvm_example.log`):
```text
UVM_ERROR [SCOREBOARD] scoreboard @ 1000ns: Data mismatch exp=0xDEAD got=0xBEEF
UVM_ERROR [SCOREBOARD] scoreboard @ 2000ns: Data mismatch exp=0x1234 got=0x5678
UVM_FATAL [TIMEOUT] tb @ 5000ns: Watchdog expired
UVM Report Summary
UVM_FATAL : 1
UVM_ERROR : 2
UVM_WARNING : 0
```

### Command:
```bash
failscope analyze examples/logs/uvm_example.log --out report.html
```

### Representative Output:
```text
Parsed 3 failure(s), 2 cluster(s) (B1)
Report written: report.html
```

**Cluster Breakdown in Report**:
- **Cluster 0 [2 failures]**: `UVM_ERROR [SCOREBOARD] scoreboard @ <TIMESTAMP>: Data mismatch exp=<HEX> got=<HEX>`
  - *Normalizes timestamps (`1000ns` / `2000ns`) and hex mismatch values, correctly recognizing that both errors share the same scoreboard failure mechanism.*
- **Cluster 1 [1 failure]**: `UVM_FATAL [TIMEOUT] tb @ <TIMESTAMP>: Watchdog expired`
  - *Isolated cleanly as a distinct fatal failure.*

---

## Supported Input Formats

| Format | Parsing Status | Notes |
| :--- | :--- | :--- |
| **Verilator Text Logs** | Supported (alpha) | Extracts `%Error: <file>:<line>` and `%Fatal:`. ANSI terminal colors stripped. |
| **UVM / SystemVerilog Logs** | Supported (alpha) | Extracts `UVM_ERROR`, `UVM_FATAL`, timestamps (`@ <t><unit>`), and scopes. |
| **Cocotb / JUnit XML** | Supported (alpha) | Standard JUnit XML `<testcase>` failure and error elements. |
| **Icarus Verilog (`iverilog`)** | Planned | Format contributions welcome. |

---

## Running the Automated Test Suite

FailScope includes a comprehensive automated test suite covering unit, integration, and regression tests:

```bash
# Run all tests
pytest

# Run with test coverage
pytest --cov=failscope --cov-report=term-missing

# Run specific categories
pytest tests/unit/
pytest tests/integration/
pytest tests/regression/
```

---

## Benchmark Suite (Synthetic Evaluation)

FailScope includes a pre-registered synthetic fault-injection benchmark for evaluating clustering approaches:

```bash
failscope benchmark --out benchmark_results/
failscope evaluate benchmark_results/
```

> **Note**: This benchmark uses entirely synthetic, template-generated logs. Historical benchmark artifacts are preserved in [`benchmark_results/`](benchmark_results/). Independent audit findings regarding held-out split limitations are documented in [`docs/REAL_WORLD_UTILITY_AUDIT.md`](docs/REAL_WORLD_UTILITY_AUDIT.md).

---

## Documentation & Governance

- [docs/FIRST_USER_PILOT.md](docs/FIRST_USER_PILOT.md): Small, privacy-conscious 30-day pilot procedure for verification leads.
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md): Exhaustive breakdown of known parsing and grouping limitations and unvalidated claims.
- [docs/PRIVACY.md](docs/PRIVACY.md): Detailed verification of local-first, zero-telemetry, and network-free data handling.
- [docs/REAL_WORLD_UTILITY_AUDIT.md](docs/REAL_WORLD_UTILITY_AUDIT.md): Independent audit of synthetic benchmark data, metric proofs, and held-out splits.
- [CONTRIBUTING.md](CONTRIBUTING.md): Guidelines for development, testing, and pull requests.
- [docs/FEEDBACK.md](docs/FEEDBACK.md): Structured template for submitting feedback without uploading proprietary RTL.
- [LICENSE](LICENSE): Released under the MIT License.
