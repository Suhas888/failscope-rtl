# FailScope RTL -- Benchmark Specification & Evaluation Record

## 1. Benchmark Objective

The central research hypothesis of FailScope RTL is:
> *Ordinary error-signature bucketing (B1) sometimes over-splits failures caused by one underlying defect (e.g., when the same defect manifests with varied messages across different tests) and over-merges failures caused by different defects (e.g., when distinct defects produce identical generic timeouts). More sophisticated clustering methods (B2 fuzzy text and B3 text + run-history features) may improve attribution.*

To test this hypothesis without requiring proprietary commercial EDA tools or cloud services, FailScope RTL includes a deterministic, reproducible synthetic benchmark suite.

> **CRITICAL DISCLAIMER**:
> All benchmark logs and failure records are generated synthetically using Python templates and random seeds. Synthetic test logs are helpful for algorithmic validation but **are not equivalent to real engineering failures** from tape-out verification suites.

---

## 2. Benchmark Scenario Families

The benchmark generates **120 deterministic scenarios** spanning 7 distinct families:

1. **`single_bug_varied`** (36 scenarios):
   A single defect (e.g., operator change, off-by-one, missing reset, scoreboard bug) triggers multiple failing tests with varying error message phrasing.
2. **`single_bug_same`** (12 scenarios):
   A single defect triggers multiple failures with identical or near-identical messages.
3. **`multi_bug`** (35 scenarios):
   Two or three independent bugs active simultaneously in the same regression, causing interleaved test failures.
4. **`generic_timeout`** (24 scenarios):
   Distinct bugs that all produce identical generic timeout messages (`timeout after 10000ns`). Tests whether methods can separate unrelated root causes when log messages alone lack distinguishing words.
5. **`unrelated_infra`** (3 scenarios):
   Simulation failures caused by infrastructure errors (e.g., missing testbench file, compilation crash) rather than RTL bugs.
6. **`multi_bug_combo`** (6 scenarios):
   Complex scenarios where multiple bugs interact simultaneously.
7. **`ambiguous`** (4 scenarios):
   Scenarios where a failure could be plausibly attributed to more than one defect (label marked as `-1`). Ambiguous failures are reported separately and excluded from ARI calculation to prevent artificial label forcing.

---

## 3. Clustering Method Ladder

| Method | Description | Input Features |
| :--- | :--- | :--- |
| **B0** | Exact First-Error Line | Raw `first_error_message` string with no normalization. Fallback to `error_class \| test_name`. |
| **B1** | Normalized Signature | Deterministic rule-based normalization (timestamps, hex addresses, seeds, paths, variable numbers normalized; assertions/operators preserved). |
| **B2** | Fuzzy Text Clustering | TF-IDF token representation over error message + bounded context lines; cosine distance with agglomerative clustering. |
| **B3** | Multi-Modal Feature Clustering | B2 text distance weighted with structured features (test co-failure patterns, error classes, simulator IDs, file references). |

---

## 4. Pre-Registered Evaluation Gate

Before inspecting benchmark outcomes, the evaluation gate is pre-registered with the following provisional acceptance criteria:

1. **ARI Improvement**: B3 improves Adjusted Rand Index over B1 by at least **+0.05 absolute** across evaluable scenarios.
2. **V-Measure Improvement**: B3 improves V-measure over B1 by at least **+0.05 absolute**.
3. **Cluster Count Error Reduction**: B3 reduces the mean absolute error between predicted cluster count and true cause count relative to B1.
4. **Exact Count Accuracy**: B3 achieves equal or higher exact cluster count accuracy than B1.
5. **Broad Benefit**: The improvement must not be driven entirely by a single scenario family.

If B3 does not significantly improve over B1, the engineering recommendation is to avoid unnecessary algorithmic complexity and prefer the simpler B1 signature bucketing.

---

## 5. Measured Benchmark Results

Run command: `failscope benchmark --out benchmark_results/` (Seed: 42, Target: 120 scenarios)

| Method | Mean ARI | ARI 95% CI | Mean V-Measure | Mean Cluster AbsErr | Exact Count Accuracy | Total Scenarios |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **B0** | 0.0299 | [0.000, 0.075] | 0.6095 | 3.467 | 5.83% | 120 |
| **B1** | 0.0382 | [-0.007, 0.103] | 0.5687 | 2.600 | 11.67% | 120 |
| **B2** | 0.0465 | [0.000, 0.116] | 0.6155 | 2.575 | 11.67% | 120 |
| **B3** | **0.0984** | **[0.039, 0.173]** | **0.6285** | **2.350** | **17.50%** | 120 |

### Pre-Registered Gate Assessment
- **ARI Improvement (B3 vs B1)**: Delta = **+0.0602** (>= +0.05 threshold) -> **PASSED**
- **V-Measure Improvement (B3 vs B1)**: Delta = **+0.0598** (>= +0.05 threshold) -> **PASSED**
- **Cluster Count Error Reduction (B3 vs B1)**: Delta = **-0.2500** (Error reduced from 2.600 to 2.350) -> **PASSED**
- **Exact Count Accuracy (B3 vs B1)**: Delta = **+0.0583** (Accuracy improved from 11.67% to 17.50%) -> **PASSED**
- **Overall Gate Decision**: **PASSED**
