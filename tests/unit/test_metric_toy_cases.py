"""
Hand-calculated toy tests for metric edge cases and scikit-learn comparisons (Audit B).

Verifies ARI, V-measure, cluster-count error, exact-count accuracy, and degenerate handling.
"""
import pytest
from sklearn.metrics import (
    adjusted_rand_score,
    v_measure_score,
    homogeneity_score,
    completeness_score,
)
from failscope.metrics import evaluate_scenario, _is_degenerate


class TestMetricToyCalculations:
    """Hand-calculated mathematical verification of clustering metrics."""

    def test_case1_perfect_match(self):
        """
        True: [0, 0, 1, 1], Pred: [0, 0, 1, 1]
        Contingency:
             Pred 0  Pred 1
        T 0    2       0   (row sum 2, C(2,2)=1)
        T 1    0       2   (row sum 2, C(2,2)=1)
        (col sums 2, 2, C(2,2)+C(2,2)=2)
        Index = 1 + 1 = 2
        Max Index = (2 + 2) / 2 = 2
        Expected Index = (2 * 2) / C(4,2) = 4 / 6 = 2/3
        ARI = (2 - 2/3) / (2 - 2/3) = 1.0
        Homogeneity = 1.0, Completeness = 1.0, V-measure = 1.0
        """
        true_labels = [0, 0, 1, 1]
        pred_labels = [0, 0, 1, 1]
        m = evaluate_scenario("TOY_01", "B1", pred_labels, true_labels)
        assert not m.degenerate
        assert m.ari == pytest.approx(1.0)
        assert m.v_measure == pytest.approx(1.0)
        assert m.homogeneity == pytest.approx(1.0)
        assert m.completeness == pytest.approx(1.0)
        assert m.abs_cluster_error == 0
        assert m.exact_count_match is True
        # Sklearn comparison
        assert m.ari == pytest.approx(adjusted_rand_score(true_labels, pred_labels))
        assert m.v_measure == pytest.approx(v_measure_score(true_labels, pred_labels))

    def test_case2_over_merging_to_single_cluster(self):
        """
        Two distinct true classes collapsed into a single predicted cluster.
        True: [0, 0, 1, 1], Pred: [0, 0, 0, 0]
        Contingency:
             Pred 0
        T 0    2      (row sum 2, C(2,2)=1)
        T 1    2      (row sum 2, C(2,2)=1)
        Col sum = 4, C(4,2) = 6
        Index = C(2,2) + C(2,2) = 2
        Expected Index = (sum_rows * sum_cols) / N = (2 * 6) / 6 = 2
        Numerator = Index - Expected = 2 - 2 = 0
        ARI = 0.0
        Homogeneity = 0.0 (cluster is impure)
        Completeness = 1.0 (all class members are together)
        V-measure = 2 * (0 * 1) / (0 + 1) = 0.0
        Abs cluster error = |1 - 2| = 1
        """
        true_labels = [0, 0, 1, 1]
        pred_labels = [0, 0, 0, 0]
        m = evaluate_scenario("TOY_02", "B3", pred_labels, true_labels)
        assert not m.degenerate
        assert m.ari == pytest.approx(0.0)
        assert m.v_measure == pytest.approx(0.0)
        assert m.homogeneity == pytest.approx(0.0)
        assert m.completeness == pytest.approx(1.0)
        assert m.abs_cluster_error == 1
        assert m.exact_count_match is False
        # Sklearn comparison
        assert m.ari == pytest.approx(adjusted_rand_score(true_labels, pred_labels))
        assert m.v_measure == pytest.approx(v_measure_score(true_labels, pred_labels))

    def test_case3_over_splitting_single_class(self):
        """
        Single true class over-split into two predicted clusters.
        True: [0, 0, 0, 0], Pred: [0, 0, 1, 1]
        Contingency:
             Pred 0  Pred 1
        T 0    2       2   (row sum 4, C(4,2)=6)
        Col sums 2, 2, C(2,2)+C(2,2)=2
        Index = C(2,2) + C(2,2) = 2
        Expected Index = (6 * 2) / 6 = 2
        Numerator = 2 - 2 = 0 -> ARI = 0.0
        Homogeneity = 1.0 (each cluster only has class 0)
        Completeness = 0.0 (class 0 split across clusters)
        V-measure = 0.0
        Abs cluster error = |2 - 1| = 1
        """
        true_labels = [0, 0, 0, 0]
        pred_labels = [0, 0, 1, 1]
        m = evaluate_scenario("TOY_03", "B0", pred_labels, true_labels)
        assert not m.degenerate
        assert m.ari == pytest.approx(0.0)
        assert m.v_measure == pytest.approx(0.0)
        assert m.homogeneity == pytest.approx(1.0)
        assert m.completeness == pytest.approx(0.0)
        assert m.abs_cluster_error == 1
        assert m.exact_count_match is False
        # Sklearn comparison
        assert m.ari == pytest.approx(adjusted_rand_score(true_labels, pred_labels))
        assert m.v_measure == pytest.approx(v_measure_score(true_labels, pred_labels))

    def test_case4_single_class_match(self):
        """
        Single true class correctly predicted as single cluster.
        True: [0, 0, 0, 0], Pred: [0, 0, 0, 0]
        ARI = 1.0, V-measure = 1.0
        """
        true_labels = [0, 0, 0, 0]
        pred_labels = [0, 0, 0, 0]
        m = evaluate_scenario("TOY_04", "B1", pred_labels, true_labels)
        assert not m.degenerate
        assert m.ari == pytest.approx(1.0)
        assert m.v_measure == pytest.approx(1.0)
        assert m.abs_cluster_error == 0
        assert m.exact_count_match is True
        # Sklearn comparison
        assert m.ari == pytest.approx(adjusted_rand_score(true_labels, pred_labels))
        assert m.v_measure == pytest.approx(v_measure_score(true_labels, pred_labels))

    def test_case5_label_permutation_invariance(self):
        """Cluster IDs are nominal integers; permutation does not affect ARI or V-measure."""
        true_labels = [0, 0, 1, 1, 2, 2]
        pred_labels_a = [0, 0, 1, 1, 2, 2]
        pred_labels_b = [2, 2, 0, 0, 1, 1]
        ma = evaluate_scenario("TOY_05A", "B1", pred_labels_a, true_labels)
        mb = evaluate_scenario("TOY_05B", "B1", pred_labels_b, true_labels)
        assert ma.ari == mb.ari == pytest.approx(1.0)
        assert ma.v_measure == mb.v_measure == pytest.approx(1.0)

    def test_case6_fractional_ari_hand_calculated(self):
        """
        True: [0, 0, 0, 1, 1, 1], Pred: [0, 0, 1, 1, 1, 1]  (n=6, C(6,2)=15)
        Contingency:
             Pred 0  Pred 1
        T 0    2       1   (row sum 3, C(3,2)=3)
        T 1    0       3   (row sum 3, C(3,2)=3)
        Col sums 2, 4 -> C(2,2)=1, C(4,2)=6 -> sum=7
        Index = C(2,2) + C(1,2) + C(0,2) + C(3,2) = 1 + 0 + 0 + 3 = 4
        Expected = (6 * 7) / 15 = 42 / 15 = 2.8
        Max = (6 + 7) / 2 = 6.5
        ARI = (4 - 2.8) / (6.5 - 2.8) = 1.2 / 3.7 = 12 / 37 ≈ 0.324324324...
        """
        true_labels = [0, 0, 0, 1, 1, 1]
        pred_labels = [0, 0, 1, 1, 1, 1]
        m = evaluate_scenario("TOY_06", "B2", pred_labels, true_labels)
        assert not m.degenerate
        expected_ari = 12.0 / 37.0
        assert m.ari == pytest.approx(expected_ari)
        assert m.ari == pytest.approx(adjusted_rand_score(true_labels, pred_labels))
        assert m.v_measure == pytest.approx(v_measure_score(true_labels, pred_labels))

    def test_case7_all_singletons_over_split(self):
        """
        True: [0, 0, 1, 1], Pred: [0, 1, 2, 3]  (maximum fragmentation into singletons)
        Contingency has all cell counts <= 1 -> Index = 0
        Expected = (2 * 0) / 6 = 0
        ARI = 0.0

        Entropy calculations for V-measure:
          H(C) = 1.0 (2 equal classes)
          H(K) = log2(4) = 2.0 (4 singleton clusters)
          H(C|K) = 0.0 (each singleton cluster is completely pure)
          H(K|C) = log2(2) = 1.0 (each class is uniformly split across 2 clusters)
          Homogeneity = 1 - H(C|K)/H(C) = 1 - 0/1 = 1.0
          Completeness = 1 - H(K|C)/H(K) = 1 - 1/2 = 0.5
          V-measure = 2 * (1.0 * 0.5) / (1.0 + 0.5) = 1.0 / 1.5 = 2/3 ≈ 0.6666666667
        """
        true_labels = [0, 0, 1, 1]
        pred_labels = [0, 1, 2, 3]
        m = evaluate_scenario("TOY_07", "B0", pred_labels, true_labels)
        assert not m.degenerate
        assert m.ari == pytest.approx(0.0)
        assert m.homogeneity == pytest.approx(1.0)
        assert m.completeness == pytest.approx(0.5)
        assert m.v_measure == pytest.approx(2.0 / 3.0)
        assert m.abs_cluster_error == abs(4 - 2) == 2
        assert m.exact_count_match is False
        # Scikit-learn validation
        assert m.ari == pytest.approx(adjusted_rand_score(true_labels, pred_labels))
        assert m.v_measure == pytest.approx(v_measure_score(true_labels, pred_labels))
        assert m.homogeneity == pytest.approx(homogeneity_score(true_labels, pred_labels))
        assert m.completeness == pytest.approx(completeness_score(true_labels, pred_labels))



class TestMetricEdgeCasesDegenerate:
    """Degenerate input validation (empty, single item, mismatched lengths)."""

    def test_empty_labels(self):
        deg, reason = _is_degenerate([], [])
        assert deg is True
        assert reason == "empty input"

    def test_single_item(self):
        deg, reason = _is_degenerate([0], [0])
        assert deg is True
        assert reason == "single record"

    def test_mismatched_lengths(self):
        m = evaluate_scenario("DEG_01", "B1", [0, 1], [0, 1, 2])
        assert m.degenerate is True
        assert "mismatched" in m.degenerate_reason
        assert m.ari is None
        assert m.v_measure is None
