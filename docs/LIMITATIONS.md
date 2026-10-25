# FailScope RTL — Known Limitations & Unvalidated Claims

FailScope RTL is an alpha research prototype designed for investigating post-simulation regression failure triage. To maintain scientific and engineering rigor, all known limitations, operational trade-offs, and unvalidated claims are documented below.

---

## 1. Scope & Non-Goals

- **Does NOT fix or modify RTL code**: FailScope RTL is strictly an investigative log analyzer. It never edits, synthesizes, or modifies Verilog, SystemVerilog, or VHDL files.
- **Does NOT guarantee root-cause localization**: Clustering groups failure *symptoms* based on normalized message text and metadata. It does not trace signals through netlists or localize the originating HDL code bug.
- **Does NOT include an RTL simulator**: FailScope does not compile or run simulations. It requires log files or JUnit XML reports produced by your existing simulation flows (Verilator, UVM, Cocotb, etc.).
- **Passing tests are NOT proof of commercial effectiveness**: The existing suite of passing automated unit and integration tests verifies internal software correctness, regex stability, and metric math. It does not constitute proof of real-world commercial triage efficacy on multi-gigabyte industrial regression suites.

---

## 2. Input & Parsing Limitations

| Input Format | Implementation Basis | Known Limitations |
| :--- | :--- | :--- |
| **Verilator Text Logs** | Regex pattern matching for `%Error: <file>:<line>` and `%Fatal:` | Interleaved output from parallel `make -j` runs can break multi-line context blocks. Compiler warnings may be treated as errors if not configured. |
| **UVM / SystemVerilog Logs** | Regex extraction of `UVM_ERROR`, `UVM_FATAL`, timestamps (`@ <t><unit>`), and component paths | Non-standard or user-overridden UVM report catchers and unstructured multi-line object print dumps are not parsed into structured fields. |
| **Cocotb / JUnit XML** | Standard `xml.etree.ElementTree` parsing of `<testcase>`, `<failure>`, `<error>` | Non-UTF8 XML entities or truncated XML files from crashed simulation runners produce parse warnings. |
| **Custom Testbenches** | Not supported out of the box | Unstructured `$display("ERROR: ...")` prints lacking standard severity tags are ignored by default. |

---

## 3. Failure Grouping & Clustering Limitations

### Baseline 1 (B1 — Normalized Signatures, Recommended Default)
- **Mechanism**: Strips dynamic runtime variables (timestamps `@ 1000ns`, hex memory addresses `0xDEADBEEF`, random seeds, long file paths, and large numbers $\ge 1000$).
- **Over-Merging Risk**: If two fundamentally different bugs emit the exact same generic error string (e.g. `%Error: Assertion failed` without file location or signal names), B1 will merge them into a single cluster card.
- **Over-Splitting Risk**: If one single root defect produces varying error messages across testcases with differing wording, B1 will present them as multiple distinct clusters.

### Baseline 3 (B3 — TF-IDF + Agglomerative Clustering, Experimental)
- **Status**: Strictly experimental research comparison.
- **Observed Defect**: Evaluation on synthetic benchmarks and sample logs showed that vector clustering on short, sparse simulation error lines suffers from severe **false merges** (for example, merging fatal watchdog timeouts with functional scoreboard mismatches into a single cluster). B1 remains the default.

---

## 4. Run Comparison Confounders

When using `failscope compare` to diff two simulation runs (e.g. Nightly Run A vs Nightly Run B):
- **Missing Version Control Information**: If git commit SHAs are not recorded in run metadata, causal attribution to a specific code commit cannot be proven.
- **Testbench Flakiness & Random Seeds**: A "newly observed" failure signature may be caused by a changed random seed, a newly introduced testcase, or an asynchronous race condition, rather than a regression in the RTL design under test.

---

## 5. Unvalidated Claims (Evidence Still Required)

The following claims must **never** be made without rigorous, pre-registered empirical evidence:

1. **"Reduces triage time by X%"**:
   - *Status*: **Unverified**.
   - *Requirement*: Requires controlled, stopwatch-measured human trials comparing verification engineers triaging raw logs vs FailScope reports on identical regressions.
2. **"99%+ Failure Identification Accuracy"**:
   - *Status*: **Unverified on Real-World Regressions**.
   - *Requirement*: Requires evaluation against a benchmark of 50+ authentic industry regression suites with ground truth confirmed by practicing verification engineers.
3. **"Universal EDA Simulator Compatibility"**:
   - *Status*: **Partial**.
   - *Requirement*: Formally tested on Verilator error formats, standard UVM strings, and JUnit XML. Proprietary vendor outputs (Synopsys VCS, Siemens Questa, Cadence Xcelium) require real-world log validation.
