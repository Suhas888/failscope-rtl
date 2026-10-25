"""
Benchmark runner for FailScope RTL.

Runs all four clustering methods (B0–B3) against the synthetic benchmark
scenarios, evaluates metrics, checks the pre-registered gate, and saves
results to a structured output directory.

Usage:
    from failscope.benchmark.runner import run_benchmark
    results = run_benchmark(output_dir="benchmark_results/")
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from failscope.benchmark.scenarios import (
    generate_scenarios,
    ScenarioFamily,
    classify_scenario_split,
)
from failscope.clustering import ClusteringConfig, run_all_methods
from failscope.metrics import (
    AggregateMetrics,
    ScenarioMetrics,
    aggregate_metrics,
    check_gate,
    evaluate_scenario,
    paired_bootstrap_ci,
)


def _labels_from_records(records: list) -> list[int]:
    """Extract ground-truth integer labels from records."""
    result = []
    for rec in records:
        bug_ids = rec.ground_truth_bug_ids
        if not bug_ids:
            result.append(-1)
        else:
            # Encode as integer hash of first bug_id
            result.append(hash(bug_ids[0]) & 0x7FFFFFFF)
    return result


def _normalise_labels(labels: list[int]) -> list[int]:
    """
    Re-map arbitrary integer labels to contiguous integers starting at 0.
    Preserves -1 as ambiguous.
    """
    mapping: dict[int, int] = {}
    counter = 0
    out = []
    for l in labels:
        if l == -1:
            out.append(-1)
        else:
            if l not in mapping:
                mapping[l] = counter
                counter += 1
            out.append(mapping[l])
    return out


def run_benchmark(
    output_dir: Optional[str | Path] = None,
    seed: int = 42,
    target_count: int = 120,
    clustering_config: Optional[ClusteringConfig] = None,
) -> dict:
    """
    Run the full synthetic benchmark and return a results dictionary.

    Parameters
    ----------
    output_dir : str | Path, optional
        Directory to save results. Created if absent.
    seed : int
        Random seed for reproducible scenario generation.
    target_count : int
        Target number of scenarios to generate.
    clustering_config : ClusteringConfig, optional
        Custom clustering parameters.

    Returns
    -------
    dict
        Contains: scenario_count, per-method AggregateMetrics, gate results,
        scenario detail list, split summaries, and generation metadata.
    """
    cfg = clustering_config or ClusteringConfig()

    print(f"[benchmark] Generating scenarios (seed={seed}, target={target_count})...")
    t0 = time.monotonic()
    scenarios = generate_scenarios(seed=seed, target_count=target_count)
    print(f"[benchmark] Generated {len(scenarios)} scenarios in {time.monotonic()-t0:.2f}s")

    # Per-method scenario metrics
    method_scenario_metrics: dict[str, list[ScenarioMetrics]] = {
        "B0": [], "B1": [], "B2": [], "B3": []
    }
    scenario_split_map: dict[str, str] = {}

    print("[benchmark] Running B0–B3 on all scenarios...")
    t0 = time.monotonic()

    for sc in scenarios:
        split_name = classify_scenario_split(sc)
        scenario_split_map[sc.scenario_id] = split_name

        # Get evaluable records (exclude ambiguous)
        eval_records, eval_true_raw = sc.get_evaluable()

        n_excl = len(sc.records) - len(eval_records)
        n_amb = sc.n_ambiguous

        if len(eval_records) < 2:
            # Ambiguous or degenerate scenario with insufficient evaluable records (< 2)
            cluster_results = run_all_methods(sc.records, cfg)
            for method, cr in cluster_results.items():
                sm = ScenarioMetrics(
                    scenario_id=sc.scenario_id,
                    method=method,
                    true_n_clusters=sc.true_n_clusters if sc.family != ScenarioFamily.AMBIGUOUS else None,
                    predicted_n_clusters=cr.n_clusters,
                    ari=None,
                    v_measure=None,
                    homogeneity=None,
                    completeness=None,
                    abs_cluster_error=(
                        abs(cr.n_clusters - sc.true_n_clusters)
                        if sc.family != ScenarioFamily.AMBIGUOUS else None
                    ),
                    exact_count_match=(
                        (cr.n_clusters == sc.true_n_clusters)
                        if sc.family != ScenarioFamily.AMBIGUOUS else None
                    ),
                    n_records=len(sc.records),
                    n_excluded=n_excl,
                    n_ambiguous=n_amb,
                    degenerate=True,
                    degenerate_reason="fewer than 2 evaluable records (ambiguous or empty)",
                )
                method_scenario_metrics[method].append(sm)
            continue

        # Normalise true labels to contiguous ints
        eval_true = _normalise_labels(eval_true_raw)

        # Run all clustering methods
        cluster_results = run_all_methods(eval_records, cfg)

        for method, cr in cluster_results.items():
            sm = evaluate_scenario(
                scenario_id=sc.scenario_id,
                method=method,
                predicted_labels=cr.labels,
                true_labels=eval_true,
                n_excluded=n_excl,
                n_ambiguous=n_amb,
            )
            method_scenario_metrics[method].append(sm)

    elapsed = time.monotonic() - t0
    print(f"[benchmark] Evaluation complete in {elapsed:.2f}s")

    # Aggregate overall per method
    aggregates: dict[str, AggregateMetrics] = {}
    for method, sms in method_scenario_metrics.items():
        aggregates[method] = aggregate_metrics(method, sms, n_bootstrap=500, bootstrap_seed=seed)

    # Gate check overall
    gate = check_gate(aggregates["B1"], aggregates["B3"], min_improvement=0.05, bootstrap_seed=seed)

    # Grouped splits evaluation
    split_summaries: dict[str, dict] = {}
    for sp in ["dev", "held_out", "cross_boundary", "multi_cause"]:
        sp_aggregates = {}
        for method, sms in method_scenario_metrics.items():
            if sp == "multi_cause":
                filtered_sms = [s for s in sms if s.true_n_clusters is not None and s.true_n_clusters > 1]
            else:
                filtered_sms = [s for s in sms if scenario_split_map.get(s.scenario_id) == sp]
            sp_aggregates[method] = aggregate_metrics(method, filtered_sms, n_bootstrap=500, bootstrap_seed=seed)
        sp_gate = check_gate(sp_aggregates["B1"], sp_aggregates["B3"], min_improvement=0.05, bootstrap_seed=seed)
        split_summaries[sp] = {
            "split": sp,
            "scenario_count": len(filtered_sms) if "filtered_sms" in locals() else 0,
            "methods": {
                m: {
                    "mean_ari": ag.mean_ari,
                    "ari_ci_95": [ag.ari_ci_low, ag.ari_ci_high],
                    "mean_v_measure": ag.mean_v_measure,
                    "v_measure_ci_95": [ag.v_measure_ci_low, ag.v_measure_ci_high],
                    "mean_abs_cluster_error": ag.mean_abs_cluster_error,
                    "exact_count_accuracy": ag.exact_count_accuracy,
                    "n_scenarios": ag.n_scenarios,
                    "n_degenerate": ag.n_degenerate,
                }
                for m, ag in sp_aggregates.items()
            },
            "gate": sp_gate,
        }

    # Print summary table
    print("\n=== Benchmark Results (Overall, n=120) ===")
    print(f"{'Method':<6} {'ARI':>8} {'V-meas':>8} {'AbsErr':>8} {'ExactAcc':>10} {'Scenarios':>10}")
    print("-" * 56)
    for m in ["B0", "B1", "B2", "B3"]:
        ag = aggregates[m]
        ari_s = f"{ag.mean_ari:.4f}" if ag.mean_ari is not None else "  N/A  "
        vm_s = f"{ag.mean_v_measure:.4f}" if ag.mean_v_measure is not None else "  N/A  "
        ae_s = f"{ag.mean_abs_cluster_error:.3f}" if ag.mean_abs_cluster_error is not None else "  N/A  "
        ea_s = f"{ag.exact_count_accuracy:.4f}" if ag.exact_count_accuracy is not None else "  N/A  "
        print(f"{m:<6} {ari_s:>8} {vm_s:>8} {ae_s:>8} {ea_s:>10} {ag.n_scenarios:>10}")

    print(f"\nOverall Gate: {gate['overall'].upper()}")
    held_gate = split_summaries["held_out"]["gate"]
    print(f"Held-Out Gate: {held_gate['overall'].upper()}")

    # Save results
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save scenario details
        scenario_data = []
        for sc in scenarios:
            scenario_data.append({
                "scenario_id": sc.scenario_id,
                "family": sc.family.value,
                "split": scenario_split_map.get(sc.scenario_id, "unknown"),
                "bug_types": sc.bug_types,
                "description": sc.description,
                "true_n_clusters": sc.true_n_clusters,
                "n_records": len(sc.records),
                "n_ambiguous": sc.n_ambiguous,
                "n_excluded": sc.n_excluded,
                "ground_truth_labels": sc.ground_truth_labels,
                "records": [r.to_dict() for r in sc.records],
            })

        with open(output_dir / "scenarios.json", "w", encoding="utf-8") as f:
            json.dump(scenario_data, f, indent=2, default=str)

        # Save per-method scenario metrics
        for method, sms in method_scenario_metrics.items():
            rows = []
            for sm in sms:
                rows.append({
                    "scenario_id": sm.scenario_id,
                    "method": sm.method,
                    "split": scenario_split_map.get(sm.scenario_id, "unknown"),
                    "true_n_clusters": sm.true_n_clusters,
                    "predicted_n_clusters": sm.predicted_n_clusters,
                    "ari": sm.ari,
                    "v_measure": sm.v_measure,
                    "homogeneity": sm.homogeneity,
                    "completeness": sm.completeness,
                    "abs_cluster_error": sm.abs_cluster_error,
                    "exact_count_match": sm.exact_count_match,
                    "n_records": sm.n_records,
                    "n_excluded": sm.n_excluded,
                    "n_ambiguous": sm.n_ambiguous,
                    "degenerate": sm.degenerate,
                    "degenerate_reason": sm.degenerate_reason,
                    "warnings": sm.warnings,
                })
            with open(output_dir / f"metrics_{method}.json", "w", encoding="utf-8") as f:
                json.dump(rows, f, indent=2)

        # Save aggregate summary
        summary = {
            "benchmark_seed": seed,
            "scenario_count": len(scenarios),
            "elapsed_seconds": elapsed,
            "note": (
                "SYNTHETIC BENCHMARK: All log content is Python-generated. "
                "Results are not equivalent to performance on real engineering failures."
            ),
            "methods": {},
            "gate": gate,
            "splits": split_summaries,
        }
        for m, ag in aggregates.items():
            summary["methods"][m] = {
                "mean_ari": ag.mean_ari,
                "ari_ci_95": [ag.ari_ci_low, ag.ari_ci_high],
                "mean_v_measure": ag.mean_v_measure,
                "v_measure_ci_95": [ag.v_measure_ci_low, ag.v_measure_ci_high],
                "mean_homogeneity": ag.mean_homogeneity,
                "mean_completeness": ag.mean_completeness,
                "mean_abs_cluster_error": ag.mean_abs_cluster_error,
                "exact_count_accuracy": ag.exact_count_accuracy,
                "n_scenarios": ag.n_scenarios,
                "n_degenerate": ag.n_degenerate,
                "n_excluded": ag.n_excluded,
            }
        with open(output_dir / "summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        # Save split-specific summaries
        for sp, sdata in split_summaries.items():
            with open(output_dir / f"summary_{sp}.json", "w", encoding="utf-8") as f:
                json.dump(sdata, f, indent=2)

        print(f"\n[benchmark] Results saved to: {output_dir.resolve()}")

    return {
        "scenario_count": len(scenarios),
        "aggregates": aggregates,
        "gate": gate,
        "splits": split_summaries,
        "scenarios": scenarios,
        "scenario_metrics": method_scenario_metrics,
    }
