"""
Evaluation metrics for FailScope RTL clustering benchmark.

Calculates:
  - Adjusted Rand Index (ARI)
  - V-measure (homogeneity, completeness)
  - True cluster count (from ground truth)
  - Predicted cluster count
  - Absolute cluster count error
  - Exact cluster count accuracy (across scenarios)
  - Bootstrap confidence intervals

IMPORTANT design constraints:
  - Ground-truth labels are provided as separate inputs, never accessed
    through the records being clustered.
  - Degenerate inputs (single class, empty) are handled explicitly.
  - Ambiguous / excluded cases are reported separately.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ScenarioMetrics:
    """Metrics for a single benchmark scenario."""
    scenario_id: str
    method: str
    true_n_clusters: Optional[int]
    predicted_n_clusters: int
    ari: Optional[float]          # None if degenerate
    v_measure: Optional[float]    # None if degenerate
    homogeneity: Optional[float]
    completeness: Optional[float]
    abs_cluster_error: Optional[int]
    exact_count_match: Optional[bool]
    n_records: int
    n_excluded: int = 0
    n_ambiguous: int = 0
    degenerate: bool = False
    degenerate_reason: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class AggregateMetrics:
    """Aggregate metrics across all scenarios for one method."""
    method: str
    n_scenarios: int
    n_degenerate: int
    n_excluded: int
    n_ambiguous: int
    mean_ari: Optional[float]
    mean_v_measure: Optional[float]
    mean_homogeneity: Optional[float]
    mean_completeness: Optional[float]
    mean_abs_cluster_error: Optional[float]
    exact_count_accuracy: Optional[float]
    ari_ci_low: Optional[float] = None
    ari_ci_high: Optional[float] = None
    v_measure_ci_low: Optional[float] = None
    v_measure_ci_high: Optional[float] = None
    scenario_metrics: list[ScenarioMetrics] = field(default_factory=list)


def _is_degenerate(
    true_labels: list[int],
    pred_labels: list[int],
    allow_single_class: bool = True,
) -> tuple[bool, str]:
    """
    Check if a label set is degenerate for metric computation.

    By default (allow_single_class=True), single-class ground truth (all same bug)
    and single predicted cluster (all merged) are evaluated with standard
    scikit-learn semantics rather than discarded:
      - 1 true class and 1 predicted cluster -> ARI=1.0, V-measure=1.0 (perfect match)
      - 1 true class and >1 predicted clusters -> ARI=0.0, V-measure=0.0 (over-split)
      - >1 true classes and 1 predicted cluster -> ARI=0.0, V-measure=0.0 (over-merged)

    Only n < 2 (empty or single record) is inherently degenerate.
    If allow_single_class=False, legacy strict mode marks single-class partitions as degenerate.
    """
    n = len(true_labels)
    if n == 0:
        return True, "empty input"
    if n == 1:
        return True, "single record"
    if not allow_single_class:
        n_true = len(set(true_labels))
        n_pred = len(set(pred_labels))
        if n_true == 1:
            return True, "single true class (all same bug)"
        if n_pred == 1:
            return True, "single predicted cluster (all merged)"
    return False, ""


def evaluate_scenario(
    scenario_id: str,
    method: str,
    predicted_labels: list[int],
    true_labels: list[int],
    n_excluded: int = 0,
    n_ambiguous: int = 0,
    allow_single_class: bool = True,
) -> ScenarioMetrics:
    """
    Calculate metrics for one scenario.

    Parameters
    ----------
    scenario_id : str
    method : str
    predicted_labels : list[int]
        Cluster assignment from clustering method.
    true_labels : list[int]
        Ground-truth bug IDs for the same records.
        Must NOT be derived from or exposed to the clustering inputs.
    n_excluded : int
        Records excluded from evaluation (ambiguous attribution).
    n_ambiguous : int
        Records with ambiguous labels retained under documented rule.
    allow_single_class : bool, default True
        Whether to evaluate single-class / single-cluster partitions using standard
        scikit-learn metric definitions (True) or treat them as degenerate (False).
    """
    from sklearn.metrics import adjusted_rand_score, v_measure_score, homogeneity_completeness_v_measure

    n = len(true_labels)
    n_pred = len(predicted_labels)

    if n != n_pred:
        return ScenarioMetrics(
            scenario_id=scenario_id,
            method=method,
            true_n_clusters=None,
            predicted_n_clusters=0,
            ari=None, v_measure=None,
            homogeneity=None, completeness=None,
            abs_cluster_error=None, exact_count_match=None,
            n_records=n, n_excluded=n_excluded, n_ambiguous=n_ambiguous,
            degenerate=True,
            degenerate_reason="mismatched label counts",
            warnings=["true_labels and predicted_labels have different lengths"],
        )

    true_n = len(set(true_labels))
    pred_n = len(set(predicted_labels))

    degenerate, reason = _is_degenerate(true_labels, predicted_labels, allow_single_class=allow_single_class)

    if degenerate:
        return ScenarioMetrics(
            scenario_id=scenario_id,
            method=method,
            true_n_clusters=true_n,
            predicted_n_clusters=pred_n,
            ari=None, v_measure=None,
            homogeneity=None, completeness=None,
            abs_cluster_error=abs(pred_n - true_n),
            exact_count_match=(pred_n == true_n),
            n_records=n, n_excluded=n_excluded, n_ambiguous=n_ambiguous,
            degenerate=True,
            degenerate_reason=reason,
        )

    ari = float(adjusted_rand_score(true_labels, predicted_labels))
    hom, comp, vmeas = homogeneity_completeness_v_measure(true_labels, predicted_labels)

    return ScenarioMetrics(
        scenario_id=scenario_id,
        method=method,
        true_n_clusters=true_n,
        predicted_n_clusters=pred_n,
        ari=ari,
        v_measure=float(vmeas),
        homogeneity=float(hom),
        completeness=float(comp),
        abs_cluster_error=abs(pred_n - true_n),
        exact_count_match=(pred_n == true_n),
        n_records=n, n_excluded=n_excluded, n_ambiguous=n_ambiguous,
    )


def bootstrap_ci(
    values: list[float],
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """
    Compute bootstrap confidence interval for the mean of `values`.

    Sampling unit is the scenario (not individual records).
    Returns (low, high) at the requested CI level.
    """
    if len(values) < 2:
        if values:
            v = values[0]
            return (v, v)
        return (0.0, 0.0)

    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_bootstrap):
        sample = [values[rng.randint(0, n - 1)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1 - ci) / 2
    lo_idx = max(0, int(alpha * n_bootstrap))
    hi_idx = min(n_bootstrap - 1, int((1 - alpha) * n_bootstrap))
    return (means[lo_idx], means[hi_idx])


def paired_bootstrap_ci(
    deltas: list[float],
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """
    Compute bootstrap confidence interval for the mean of paired differences.

    deltas[i] = metric_candidate[i] - metric_baseline[i] for each scenario i.
    Returns (low, high) at requested CI level.
    """
    if len(deltas) < 2:
        if deltas:
            v = deltas[0]
            return (v, v)
        return (0.0, 0.0)

    rng = random.Random(seed)
    n = len(deltas)
    means = []
    for _ in range(n_bootstrap):
        sample = [deltas[rng.randint(0, n - 1)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = (1 - ci) / 2
    lo_idx = max(0, int(alpha * n_bootstrap))
    hi_idx = min(n_bootstrap - 1, int((1 - alpha) * n_bootstrap))
    return (means[lo_idx], means[hi_idx])


def aggregate_metrics(
    method: str,
    scenario_results: list[ScenarioMetrics],
    n_bootstrap: int = 1000,
    bootstrap_seed: int = 42,
) -> AggregateMetrics:
    """
    Aggregate per-scenario metrics into summary statistics with CIs.
    """
    non_degenerate = [s for s in scenario_results if not s.degenerate]
    n_deg = len(scenario_results) - len(non_degenerate)
    n_excl = sum(s.n_excluded for s in scenario_results)
    n_amb = sum(s.n_ambiguous for s in scenario_results)

    ari_vals = [s.ari for s in non_degenerate if s.ari is not None]
    vm_vals = [s.v_measure for s in non_degenerate if s.v_measure is not None]
    hom_vals = [s.homogeneity for s in non_degenerate if s.homogeneity is not None]
    comp_vals = [s.completeness for s in non_degenerate if s.completeness is not None]
    abs_err_vals = [s.abs_cluster_error for s in scenario_results if s.abs_cluster_error is not None]
    exact_vals = [s.exact_count_match for s in scenario_results if s.exact_count_match is not None]

    def safe_mean(vals):
        return float(np.mean(vals)) if vals else None

    ari_ci = bootstrap_ci(ari_vals, n_bootstrap, seed=bootstrap_seed) if len(ari_vals) >= 2 else None
    vm_ci = bootstrap_ci(vm_vals, n_bootstrap, seed=bootstrap_seed) if len(vm_vals) >= 2 else None

    return AggregateMetrics(
        method=method,
        n_scenarios=len(scenario_results),
        n_degenerate=n_deg,
        n_excluded=n_excl,
        n_ambiguous=n_amb,
        mean_ari=safe_mean(ari_vals),
        mean_v_measure=safe_mean(vm_vals),
        mean_homogeneity=safe_mean(hom_vals),
        mean_completeness=safe_mean(comp_vals),
        mean_abs_cluster_error=safe_mean(abs_err_vals),
        exact_count_accuracy=(
            float(np.mean([1 if v else 0 for v in exact_vals])) if exact_vals else None
        ),
        ari_ci_low=ari_ci[0] if ari_ci else None,
        ari_ci_high=ari_ci[1] if ari_ci else None,
        v_measure_ci_low=vm_ci[0] if vm_ci else None,
        v_measure_ci_high=vm_ci[1] if vm_ci else None,
        scenario_metrics=scenario_results,
    )


def check_gate(
    b1_metrics: AggregateMetrics,
    b3_metrics: AggregateMetrics,
    min_improvement: float = 0.05,
    bootstrap_seed: int = 42,
) -> dict:
    """
    Evaluate the pre-registered benchmark gate.

    Gate (provisional, pre-registered in docs/BENCHMARK.md):
      - B3 improves ARI over B1 by >= min_improvement absolute.
      - B3 improves V-measure over B1 by >= min_improvement absolute.
      - B3 reduces abs_cluster_error vs B1.
      - B3 improves exact_count_accuracy vs B1.

    Also calculates exact paired differences and bootstrap 95% CIs when
    scenario_metrics are available on both aggregate metrics objects.

    Returns a dict with gate fields and overall 'passed' / 'failed' / 'inconclusive'.
    """
    results = {}

    def _cmp(b1_val, b3_val, metric, higher_is_better=True):
        if b1_val is None or b3_val is None:
            results[metric] = {"result": "inconclusive", "b1": b1_val, "b3": b3_val}
            return
        delta = b3_val - b1_val
        if higher_is_better:
            passed = delta >= min_improvement
        else:
            passed = delta <= -min_improvement
        results[metric] = {
            "result": "passed" if passed else "failed",
            "b1": b1_val,
            "b3": b3_val,
            "delta": delta,
            "threshold": min_improvement,
        }

    _cmp(b1_metrics.mean_ari, b3_metrics.mean_ari, "ari_improvement", higher_is_better=True)
    _cmp(b1_metrics.mean_v_measure, b3_metrics.mean_v_measure, "v_measure_improvement", higher_is_better=True)
    _cmp(b1_metrics.mean_abs_cluster_error, b3_metrics.mean_abs_cluster_error,
         "cluster_error_reduction", higher_is_better=False)
    _cmp(b1_metrics.exact_count_accuracy, b3_metrics.exact_count_accuracy,
         "exact_count_accuracy", higher_is_better=True)

    # Compute paired differences across matching non-degenerate scenarios
    if b1_metrics.scenario_metrics and b3_metrics.scenario_metrics:
        b1_map = {s.scenario_id: s for s in b1_metrics.scenario_metrics if not s.degenerate}
        b3_map = {s.scenario_id: s for s in b3_metrics.scenario_metrics if not s.degenerate}
        common_ids = sorted(set(b1_map.keys()) & set(b3_map.keys()))
        if common_ids:
            ari_diffs = [
                b3_map[i].ari - b1_map[i].ari
                for i in common_ids
                if b3_map[i].ari is not None and b1_map[i].ari is not None
            ]
            vm_diffs = [
                b3_map[i].v_measure - b1_map[i].v_measure
                for i in common_ids
                if b3_map[i].v_measure is not None and b1_map[i].v_measure is not None
            ]
            ae_diffs = [
                b3_map[i].abs_cluster_error - b1_map[i].abs_cluster_error
                for i in common_ids
                if b3_map[i].abs_cluster_error is not None and b1_map[i].abs_cluster_error is not None
            ]
            ex_diffs = [
                (1.0 if b3_map[i].exact_count_match else 0.0) - (1.0 if b1_map[i].exact_count_match else 0.0)
                for i in common_ids
                if b3_map[i].exact_count_match is not None and b1_map[i].exact_count_match is not None
            ]

            if ari_diffs and "ari_improvement" in results:
                results["ari_improvement"]["paired_mean"] = float(np.mean(ari_diffs))
                results["ari_improvement"]["paired_ci_95"] = list(
                    paired_bootstrap_ci(ari_diffs, seed=bootstrap_seed)
                )
            if vm_diffs and "v_measure_improvement" in results:
                results["v_measure_improvement"]["paired_mean"] = float(np.mean(vm_diffs))
                results["v_measure_improvement"]["paired_ci_95"] = list(
                    paired_bootstrap_ci(vm_diffs, seed=bootstrap_seed)
                )
            if ae_diffs and "cluster_error_reduction" in results:
                results["cluster_error_reduction"]["paired_mean"] = float(np.mean(ae_diffs))
                results["cluster_error_reduction"]["paired_ci_95"] = list(
                    paired_bootstrap_ci(ae_diffs, seed=bootstrap_seed)
                )
            if ex_diffs and "exact_count_accuracy" in results:
                results["exact_count_accuracy"]["paired_mean"] = float(np.mean(ex_diffs))
                results["exact_count_accuracy"]["paired_ci_95"] = list(
                    paired_bootstrap_ci(ex_diffs, seed=bootstrap_seed)
                )

    # Overall gate
    statuses = [r["result"] for r in results.values() if isinstance(r, dict) and "result" in r]
    if "inconclusive" in statuses:
        overall = "inconclusive"
    elif all(s == "passed" for s in statuses):
        overall = "passed"
    else:
        overall = "failed"

    results["overall"] = overall
    results["min_improvement_threshold"] = min_improvement
    return results
