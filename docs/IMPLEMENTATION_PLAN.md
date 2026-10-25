# FailScope RTL -- Implementation Plan & Execution Record

## 1. Project Overview

FailScope RTL is a local-first RTL simulation regression failure investigator designed to help FPGA developers and RTL verification engineers group repetitive simulation failures into organized, evidence-backed reports.

Primary principles:
- Free and open-source development (MIT License).
- Zero required cloud services, paid accounts, or LLM APIs.
- Local processing by default.
- Deterministic, reproducible algorithms and automated tests.
- Explainable grouping linked directly to raw log evidence.
- No fabricated root causes, benchmark results, or performance claims.

---

## 2. Phased Build Sequence

### Phase A: Skeleton, Models, and Test Harness
- [x] Workspace inspection and environment discovery.
- [x] `pyproject.toml` definition with explicit dependencies (`scikit-learn`, `numpy`, `pytest`, `pytest-cov`).
- [x] Canonical data model (`src/failscope/models.py`): `FailureRecord`, `RunMetadata`, `ParseResult`, `FieldProvenance`, `FieldSource`.
- [x] Conftest and initial model tests (`tests/conftest.py`, `tests/unit/test_models.py`).

### Phase B: Parsers and Deterministic B0/B1 Clustering
- [x] Verilator log parser (`src/failscope/parsers/verilator.py`).
- [x] Cocotb / JUnit XML parser (`src/failscope/parsers/cocotb.py`).
- [x] UVM log parser (`src/failscope/parsers/uvm.py`).
- [x] Unified ingest & format detection (`src/failscope/ingest.py`).
- [x] Normalization signatures and B0/B1 key computation (`src/failscope/signatures.py`).
- [x] Unit test suites for parsers and signatures (`test_parser_*.py`, `test_signatures.py`).

### Phase C: Synthetic Fault-Injection Benchmark & Metrics
- [x] Deterministic scenario generator (`src/failscope/benchmark/scenarios.py`) spanning 7 scenario families and 120 scenarios.
- [x] Strict isolation between ground-truth labels and clustering features.
- [x] Evaluation metrics (`src/failscope/metrics.py`): ARI, V-measure, cluster error, exact accuracy, and bootstrap confidence intervals.
- [x] Pre-registered benchmark gate in `docs/BENCHMARK.md`.

### Phase D: Advanced Clustering Ladder (B2 & B3)
- [x] Feature extraction module (`src/failscope/features.py`): TF-IDF text representation and structured metadata features.
- [x] B2 fuzzy text clustering (`src/failscope/clustering.py`): TF-IDF cosine distance with agglomerative clustering.
- [x] B3 text + run-history / metadata clustering (`src/failscope/clustering.py`).
- [x] Unit tests for all clustering methods (`test_clustering.py`).

### Phase E: Run Comparison & SQLite Storage
- [x] Regression comparison engine (`src/failscope/comparison.py`): identifies newly observed, disappeared, and persistent failures with conservative language.
- [x] Versioned SQLite storage (`src/failscope/database.py`) with strict privacy (no ground-truth leak, no environment/secret storage).
- [x] Unit tests for comparison and database (`test_comparison.py`, `test_database.py`).

### Phase F: CLI & HTML Report
- [x] Standalone, full-featured CLI (`src/failscope/cli.py`): `parse`, `analyze`, `compare`, `benchmark`, `evaluate`, `doctor`, `version`.
- [x] Cross-platform Windows/Linux safe console output.
- [x] Self-contained, responsive offline HTML report generator (`src/failscope/reporting.py`) with strict XSS escaping and zero CDN/network dependencies.

### Phase G: Quality Assurance, Regression Suite & Documentation
- [x] Integration test suite (`tests/integration/test_end_to_end.py`).
- [x] Comprehensive regression test suite (`tests/regression/test_regression_cases.py`).
- [x] Full documentation: `ENVIRONMENT.md`, `ARCHITECTURE.md`, `BENCHMARK.md`, `LIMITATIONS.md`, `CONTRIBUTING.md`.

### Phase H: Verification & Final Acceptance Audit
- [x] Full test suite execution: 145/145 passing tests.
- [x] Benchmark execution (120 synthetic scenarios) and gate evaluation.
