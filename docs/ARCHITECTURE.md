# FailScope RTL -- Architecture Specification

## 1. System Overview

FailScope RTL is architected as a modular, local-first Python library and CLI tool. It processes raw simulation logs, maps them into a canonical data representation, performs deterministic or statistical clustering, and renders standalone HTML reports and run diffs.

```
       +-----------------------+
       |   Raw Simulation Log  | (Verilator / Cocotb XML / UVM)
       +-----------+-----------+
                   |
                   v
       +-----------------------+
       |     Ingest Engine     | Format detection & parser dispatch
       +-----------+-----------+
                   |
                   v
       +-----------------------+
       | Canonical Failure     | Typed internal FailureRecord model
       | Model & Provenance    | (Strict ground-truth label isolation)
       +-----------+-----------+
                   |
       +-----------+-----------+
       |                       |
       v                       v
+--------------+        +---------------+
|  Clustering  |        |      Run      |
|    Ladder    |        |  Comparison   |
| (B0,B1,B2,B3)|        |    Engine     |
+-------+------+        +-------+-------+
        \                      /
         \                    /
          v                  v
     +----------------------------+
     |   Self-Contained Report    |
     |          Generator         |
     +--------------+-------------+
                    |
                    v
          [ report.html ] (Zero external runtime dependencies, XSS-escaped)
```

---

## 2. Core Subsystems

### A. Ingest & Parsers (`failscope/ingest.py`, `failscope/parsers/`)
- **`ingest.py`**: Heuristically detects file formats based on file extension and initial buffer contents (XML roots, UVM tokens, Verilator `%Error` tokens).
- **`parsers/verilator.py`**: Parses Verilator text logs, extracts source locations (`file.v:line`), error classes (`assertion`, `%Error`), and bounded context lines.
- **`parsers/cocotb.py`**: Parses JUnit XML result files produced by cocotb and other runners. Correctly parses `<testsuites>` and `<testcase>` hierarchies without treating every failed test as a distinct defect.
- **`parsers/uvm.py`**: Parses standard UVM simulation outputs, capturing `UVM_ERROR`, `UVM_FATAL`, component paths, report IDs, and simulation timestamps.

### B. Canonical Failure Record (`failscope/models.py`)
- Represents every observed simulation failure as an immutable, typed `FailureRecord`.
- **Field Provenance**: Explicitly tracks the source of each field (`observed`, `inferred`, `unavailable`, `default`).
- **Ground-Truth Isolation**: The benchmark label field `ground_truth_bug_ids` is strictly excluded from `to_dict()`, SQLite storage, and clustering feature extractors.

### C. Normalization & Signatures (`failscope/signatures.py`)
- Computes deterministic string keys for B0 and B1 clustering.
- **B0**: Uses exact raw first-error lines with fallback to `error_class | test_name`.
- **B1**: Applies deterministic normalization:
  - Replaces ISO-8601 timestamps and clock times with `<TIMESTAMP>`.
  - Replaces hexadecimal numbers (`0x...`) with `<ADDR>`.
  - Replaces seed declarations (`seed=...`) with `<SEED>`.
  - Replaces long absolute file paths with `<PATH>`.
  - Replaces isolated large numbers (>= 4 digits) with `<N>`.
  - Normalizes redundant whitespace while strictly preserving operator syntax (`==`, `!=`, `<`, `>`).

### D. Clustering Ladder (`failscope/clustering.py`)
- **B0**: Exact line matching.
- **B1**: Normalized signature grouping.
- **B2**: TF-IDF token vectorization over error message + context lines; agglomerative clustering with cosine distance.
- **B3**: Weighted combination of B2 textual distance and structured metadata features (test co-failure patterns, simulator IDs, file references).

### E. Run Comparison (`failscope/comparison.py`)
- Compares baseline vs candidate runs.
- Categorizes signatures into `new`, `disappeared`, and `persistent`.
- Detects test state transitions (`pass_to_fail`, `fail_to_pass`).
- Uses conservative terminology (*"newly observed failure"* rather than *"confirmed regression"*) when commit history is unavailable.

### F. Standalone Reporting (`failscope/reporting.py`)
- Renders an offline-capable HTML report.
- Features dark-mode technical styling, summary cards, and collapsible cluster cards.
- **Security**: Escapes all user log inputs with `html.escape()`. Zero external CDN or script dependencies.

### G. Local SQLite Storage (`failscope/database.py`)
- Optional local database storage with schema versioning.
- Provides persistent run history for regression comparison across development sessions.
