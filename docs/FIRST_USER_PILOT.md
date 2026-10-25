# FailScope RTL — First Customer Validation Pilot Guide

## 1. Overview & Current Capabilities

FailScope RTL is a **local-first, offline post-simulation regression failure triage tool** designed for RTL verification engineers and FPGA/ASIC developers. It analyzes regression output logs and XML test reports to aggregate repetitive failures, eliminate noise, and identify regressions across simulation runs.

### What FailScope Does Today
- **Deterministic Log Parsing**:
  - **Verilator Logs**: Extracts `%Error: <file>:<line>` and `%Fatal:` markers, context lines, and file/line locations. ANSI terminal color escape codes are automatically stripped.
  - **UVM / SystemVerilog Logs**: Extracts `UVM_ERROR`, `UVM_FATAL`, simulation timestamps (`@ <time><unit>`), error tags, and hierarchical component scopes.
  - **Cocotb / JUnit XML**: Extracts test names, class names, failure/error text, and assertion failure details from standard regression test suites.
- **Noise-Reduced Signature Normalization (Baseline 1 - B1, Default)**:
  - Normalizes dynamic fields across runs: timestamps (e.g., `@ 1000ns`), hex memory addresses (e.g., `0xDEADBEEF`), random seeds, long file paths, and thread IDs.
  - Groups identical failure root mechanisms into representative cluster cards with occurrence counts and raw evidence context lines.
- **Run-over-Run Diffing (`compare`)**:
  - Compares two simulation runs (e.g., Nightly Run A vs Nightly Run B).
  - Categorizes signatures into `NEW_FAILURES` (new bugs), `RESOLVED` (fixed bugs), and `PERSISTENT` (ongoing failures).
- **Single-File Self-Contained HTML Reports**:
  - Produces standalone HTML reports with inline CSS and zero external JavaScript dependencies or CDNs.
  - Fully escaped against XSS (`html.escape` on all error messages, test names, and context lines).
  - Openable locally in any browser on air-gapped workstations.
- **Privacy & Security by Design**:
  - **100% offline**: Zero telemetry, zero external network requests, zero proprietary cloud APIs.
  - Non-destructive: Operates in read-only mode on input logs and test results.

---

## 2. Installation and Usage Instructions

### Requirements
- Python 3.10 or higher.
- Standard Python virtual environment.
- No simulator installations (Verilator/VCS) required to run FailScope itself; it operates strictly on generated log and XML files.

### Step 1: Set Up Local Environment
```powershell
# In PowerShell (Windows)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```
```bash
# In Bash (Linux/macOS)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Step 2: Verify Installation
```bash
failscope doctor
```
Expected output:
- Python version >= 3.10
- Simulator discovery check (notes whether `verilator`, `iverilog`, or commercial EDA tools are present on `PATH`)
- Package dependency check

### Step 3: Core Commands

#### 1. Analyze a Regression Log (Generate JSON + HTML Report)
```bash
failscope analyze --log examples/logs/uvm_example.log --format uvm --output-dir artifacts/uvm_run --html
```
- Outputs:
  - `artifacts/uvm_run/failures.json`: Extracted failure records.
  - `artifacts/uvm_run/clusters.json`: Grouped failure signatures.
  - `artifacts/uvm_run/report.html`: Standalone visual report.

#### 2. Parse Logs Without Full Analysis
```bash
failscope parse --log examples/logs/verilator_example.log --format verilator --output-dir artifacts/verilator_parsed
```

#### 3. Compare Two Regression Runs
```bash
failscope compare --baseline-run artifacts/run_monday --current-run artifacts/run_tuesday --output-dir artifacts/run_diff --html
```

---

## 4. Reproducible Demonstration

FailScope includes verified example logs in `examples/logs/` demonstrating each supported format.

### Demo 1: UVM Regression Log Analysis
Run:
```bash
failscope analyze --log examples/logs/uvm_example.log --format uvm --output-dir artifacts/demo_uvm --html
```
**Observed Behavior**:
- Input: 3 failures across 5 simulation lines.
  - Line 1: `UVM_ERROR [SCB] scoreboard @ 1000ns: data mismatch: expected 0xDEAD, got 0xBEEF`
  - Line 2: `UVM_ERROR [SCB] scoreboard @ 2000ns: data mismatch: expected 0x1234, got 0x5678`
  - Line 3: `UVM_FATAL [TIMEOUT] tb_top.watchdog @ 5000ns: simulation watchdog expired`
- **B1 Result**:
  - 2 distinct clusters formed:
    1. Scoreboard Data Mismatch (Count: 2): Normalizes `1000ns` / `2000ns` and hex values into `<TIMESTAMP>` and `<HEX>`, correctly recognizing both as the same scoreboard failure type.
    2. Watchdog Timeout (Count: 1): Kept strictly isolated as a distinct fatal failure.
- HTML report generated at `artifacts/demo_uvm/report.html`.

### Demo 2: Verilator Error Log Analysis
Run:
```bash
failscope analyze --log examples/logs/verilator_example.log --format verilator --output-dir artifacts/demo_verilator --html
```
**Observed Behavior**:
- Input: 3 Verilator errors across 2 source locations.
  - 2 errors at `sim_main.cpp:42: %Error: Assertion failed`
  - 1 error at `sim_main.cpp:57: %Fatal: Test timeout`
- **B1 Result**:
  - Grouped into 2 distinct clusters by file location and normalized failure message.

### Demo 3: Cocotb JUnit XML Analysis
Run:
```bash
failscope analyze --log examples/logs/junit_example.xml --format junit --output-dir artifacts/demo_junit --html
```
**Observed Behavior**:
- Input: 3 tests (1 pass, 2 failures).
- **B1 Result**:
  - Passing test filtered out cleanly.
  - 2 failures parsed, categorized, and summarized.

---

## 5. Known Limitations

1. **Rule-Based Parsing (Not an AST/EDA Compiler)**:
   - FailScope parses text lines matching standard Verilator (`%Error`, `%Fatal`), UVM (`UVM_ERROR`, `UVM_FATAL`, `UVM_WARNING`), and JUnit XML tags.
   - Non-standard user `$display("ERROR: ...")` prints without standard severity prefixes will not be detected without custom regex configuration.
2. **Signature Split/Merge Trade-offs (B1)**:
   - **Potential False Merges**: If two distinct bugs throw the exact same message string (e.g., generic `Assertion failed` without source line or expression), B1 groups them together.
   - **Potential False Splits**: If identical root bugs produce slightly different text wording that does not match normalization patterns, B1 will treat them as separate clusters.
3. **Machine Learning / Vector Clustering (B3) is Experimental**:
   - The optional `--method b3` (TF-IDF + Agglomerative Clustering) demonstrated false merges on sparse, single-line error messages during synthetic and sample evaluations (e.g., merging timeouts with data mismatches).
   - **Policy**: B1 remains the default and recommended method. B3 is retained only for experimental research comparison.
4. **Log Size & Memory Scaling**:
   - Tested on logs up to several thousand lines. Log files exceeding gigabytes should be pre-filtered or evaluated under supervision to monitor memory consumption.
5. **No Native Simulator Bundled**:
   - FailScope does not simulate RTL code; it requires logs generated by your existing simulation flow (VCS, Questa, Xcelium, Verilator, Icarus, or Cocotb).

---

## 6. Small, Privacy-Conscious Pilot Procedure (30-Day Evaluation)

This protocol is designed for verification leads to evaluate FailScope with **zero risk of intellectual property leakage or disruption to existing toolchains**.

### Evaluation Protocol

| Phase | Duration | Objective | Required Data |
| :--- | :--- | :--- | :--- |
| **Phase 1: Setup & Doctor** | Day 1 | Verify local installation in isolated environment. | None (self-test) |
| **Phase 2: Local Log Parsing** | Days 2–5 | Run FailScope on 3–5 representative regression logs. | Local log files only (no source code required) |
| **Phase 3: Engineer Review** | Days 6–15 | Verification engineer evaluates cluster cards against manual triage. | Qualitative assessment sheet |
| **Phase 4: Run Diffing** | Days 16–25 | Test `failscope compare` across consecutive nightly runs. | Consecutive regression run logs |
| **Phase 5: Pilot Decision** | Days 26–30 | Synthesize findings: accuracy, false merges/splits, time impact. | Final pilot review |

### Privacy & Data Safety Guarantees
1. **Air-Gapped Operation**: FailScope runs with no internet connection. You can disable all network adapters during execution.
2. **No Proprietary RTL Required**: FailScope only inspects log text or JUnit XML. Verilog/SystemVerilog source files do not need to be provided or referenced.
3. **Local Directory Confinement**: All outputs are written strictly to the `--output-dir` path specified in the command. No background caches or external servers are contacted.

### Engineer Evaluation Checklist
During Phase 3 and 4, the verification engineer should score FailScope on:
- [ ] **Parse Coverage**: Did FailScope extract 100% of the regression failures identified by your regression manager?
- [ ] **Cluster Quality**: Did identical bugs with different timestamps/seeds collapse into a single cluster card?
- [ ] **False Merges**: Did unrelated bugs collapse into the same card? (Target: 0 critical false merges).
- [ ] **Noise Reduction**: How many total raw failure lines existed vs how many cluster cards were presented?
- [ ] **Regression Diffing**: Did `failscope compare` accurately flag new failing tests vs persistent ones?

---

## 7. Evidence Still Needed Before Commercial Claims

To maintain scientific and commercial integrity, the following claims must **never** be made until backed by formal, measured evidence:

1. **"Reduces Triage Time by X%"**:
   - *Status*: **Unverified**.
   - *Evidence Needed*: Controlled, stopwatch-measured human trials comparing engineers triaging raw logs vs FailScope reports on identical regressions.
2. **"99%+ Failure Identification Accuracy"**:
   - *Status*: **Unverified on Real-World Logs**.
   - *Evidence Needed*: Evaluation against a benchmark of 50+ diverse, authentic industry regression suites with ground-truth root causes confirmed by verification leads.
3. **"Automated Root Cause Localization"**:
   - *Status*: **Not Supported**.
   - *Clarification*: FailScope performs failure grouping and symptom triage, not automatic RTL bug localization in source code.
4. **"Full Compatibility with All Simulators"**:
   - *Status*: **Partial**.
   - *Clarification*: Formally tested on Verilator error formats, UVM standard reporter strings, and JUnit XML. Proprietary simulator log dialects (Synopsys VCS, Siemens Questa, Cadence Xcelium) require evaluation on real outputs to confirm regex coverage.
