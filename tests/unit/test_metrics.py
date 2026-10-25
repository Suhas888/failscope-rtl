"""Unit tests for evaluation metrics module."""
import pytest
from failscope.metrics import (
    evaluate_scenario,
    aggregate_metrics,
    bootstrap_ci,
    check_gate,
    ScenarioMetrics,
    AggregateMetrics,
)


class TestEvaluateScenario:
    def test_perfect_clustering(self):
        true_labels = [0, 0, 1, 1, 2, 2]
        pred_labels = [0, 0, 1, 1, 2, 2]
        m = evaluate_scenario("S001", "B1", pred_labels, true_labels)
        assert not m.degenerate
        assert m.ari == pytest.approx(1.0)
        assert m.v_measure == pytest.approx(1.0)
        assert m.abs_cluster_error == 0
        assert m.exact_count_match is True

    def test_permuted_cluster_ids_still_perfect(self):
        """Cluster IDs are arbitrary labels, so permutation should still be ARI=1.0."""
        true_labels = [0, 0, 1, 1]
        pred_labels = [1, 1, 0, 0]
        m = evaluate_scenario("S002", "B2", pred_labels, true_labels)
        assert not m.degenerate
        assert m.ari == pytest.approx(1.0)
        assert m.v_measure == pytest.approx(1.0)

    def test_mismatched_lengths(self):
        m = evaluate_scenario("S003", "B0", [0, 1], [0, 1, 2])
        assert m.degenerate is True
        assert "mismatched label counts" in m.degenerate_reason
        assert len(m.warnings) > 0

    def test_single_class_handling(self):
        """Single true class with perfect prediction gives ARI=1.0 by default, degenerate if allow_single_class=False."""
        true_labels = [0, 0, 0, 0]
        pred_labels = [0, 0, 0, 0]
        # Default sklearn behavior
        m_default = evaluate_scenario("S004", "B1", pred_labels, true_labels)
        assert m_default.degenerate is False
        assert m_default.ari == pytest.approx(1.0)
        assert m_default.v_measure == pytest.approx(1.0)
        assert m_default.exact_count_match is True

        # Legacy strict mode
        m_legacy = evaluate_scenario("S004", "B1", pred_labels, true_labels, allow_single_class=False)
        assert m_legacy.degenerate is True
        assert m_legacy.ari is None
        assert m_legacy.v_measure is None
        assert m_legacy.exact_count_match is True

    def test_imperfect_clustering(self):
        true_labels = [0, 0, 1, 1]
        pred_labels = [0, 1, 1, 1]
        m = evaluate_scenario("S005", "B3", pred_labels, true_labels)
        assert not m.degenerate
        assert 0.0 <= m.ari <= 1.0
        assert 0.0 <= m.v_measure <= 1.0


class TestBootstrapCI:
    def test_ci_interval(self):
        values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        low, high = bootstrap_ci(values, n_bootstrap=500, ci=0.95, seed=42)
        mean_val = sum(values) / len(values)
        assert low <= mean_val <= high
        assert low < high

    def test_single_or_empty_values(self):
        assert bootstrap_ci([]) == (0.0, 0.0)
        assert bootstrap_ci([0.5]) == (0.5, 0.5)

    def test_paired_bootstrap_ci(self):
        from failscope.metrics import paired_bootstrap_ci
        deltas = [0.05, 0.06, 0.04, 0.05, 0.07, 0.03]
        low, high = paired_bootstrap_ci(deltas, n_bootstrap=500, ci=0.95, seed=42)
        mean_delta = sum(deltas) / len(deltas)
        assert low <= mean_delta <= high
        assert low > 0.0  # strictly positive difference



class TestAggregateAndGate:
    def test_aggregate_metrics(self):
        m1 = evaluate_scenario("S1", "B1", [0, 0, 1, 1], [0, 0, 1, 1])
        m2 = evaluate_scenario("S2", "B1", [0, 1, 1, 1], [0, 0, 1, 1])
        agg = aggregate_metrics("B1", [m1, m2])
        assert agg.n_scenarios == 2
        assert agg.n_degenerate == 0
        assert agg.mean_ari is not None
        assert agg.mean_v_measure is not None

    def test_check_gate_passed(self):
        b1 = AggregateMetrics(
            method="B1", n_scenarios=10, n_degenerate=0, n_excluded=0, n_ambiguous=0,
            mean_ari=0.40, mean_v_measure=0.50, mean_homogeneity=0.50,
            mean_completeness=0.50, mean_abs_cluster_error=2.0, exact_count_accuracy=0.20,
        )
        b3 = AggregateMetrics(
            method="B3", n_scenarios=10, n_degenerate=0, n_excluded=0, n_ambiguous=0,
            mean_ari=0.48, mean_v_measure=0.58, mean_homogeneity=0.58,
            mean_completeness=0.58, mean_abs_cluster_error=1.5, exact_count_accuracy=0.30,
        )
        gate = check_gate(b1, b3, min_improvement=0.05)
        assert gate["overall"] == "passed"
        assert gate["ari_improvement"]["result"] == "passed"
        assert gate["v_measure_improvement"]["result"] == "passed"
        assert gate["cluster_error_reduction"]["result"] == "passed"
        assert gate["exact_count_accuracy"]["result"] == "passed"

    def test_check_gate_failed(self):
        b1 = AggregateMetrics(
            method="B1", n_scenarios=10, n_degenerate=0, n_excluded=0, n_ambiguous=0,
            mean_ari=0.50, mean_v_measure=0.60, mean_homogeneity=0.60,
            mean_completeness=0.60, mean_abs_cluster_error=1.0, exact_count_accuracy=0.50,
        )
        b3 = AggregateMetrics(
            method="B3", n_scenarios=10, n_degenerate=0, n_excluded=0, n_ambiguous=0,
            mean_ari=0.51, mean_v_measure=0.61, mean_homogeneity=0.61,
            mean_completeness=0.61, mean_abs_cluster_error=1.0, exact_count_accuracy=0.50,
        )
        gate = check_gate(b1, b3, min_improvement=0.05)
        assert gate["overall"] == "failed"
