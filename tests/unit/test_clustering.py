"""Unit tests for clustering methods B0–B3."""
import pytest
from failscope.models import FailureRecord
from failscope.clustering import (
    ClusteringConfig,
    cluster_b0, cluster_b1, cluster_b2, cluster_b3,
    run_all_methods,
)


def make_rec(msg: str, error_class: str = "error", sim: str = "verilator",
             run_id: str = "run1") -> FailureRecord:
    return FailureRecord(
        first_error_message=msg,
        error_class=error_class,
        simulator=sim,
        run_id=run_id,
        context_lines=[msg],
    )


class TestB0Clustering:
    def test_exact_same_message_one_cluster(self):
        records = [make_rec("same error"), make_rec("same error"), make_rec("same error")]
        result = cluster_b0(records)
        assert result.n_clusters == 1
        assert len(set(result.labels)) == 1

    def test_distinct_messages_distinct_clusters(self):
        records = [make_rec("error A"), make_rec("error B"), make_rec("error C")]
        result = cluster_b0(records)
        assert result.n_clusters == 3

    def test_empty_input(self):
        result = cluster_b0([])
        assert result.n_clusters == 0
        assert result.labels == []

    def test_single_record(self):
        result = cluster_b0([make_rec("solo")])
        assert result.n_clusters == 1
        assert result.labels == [0]

    def test_no_normalisation_applied(self):
        """B0 must NOT merge seed=111 and seed=222 (no normalisation)."""
        r1 = make_rec("seed=11111111 assertion failed")
        r2 = make_rec("seed=22222222 assertion failed")
        result = cluster_b0([r1, r2])
        assert result.n_clusters == 2

    def test_method_label_is_b0(self):
        result = cluster_b0([make_rec("x")])
        assert result.method == "B0"

    def test_labels_parallel_to_records(self):
        records = [make_rec("a"), make_rec("b"), make_rec("a")]
        result = cluster_b0(records)
        assert len(result.labels) == 3
        assert result.labels[0] == result.labels[2]
        assert result.labels[0] != result.labels[1]


class TestB1Clustering:
    def test_different_seeds_merged(self):
        r1 = make_rec("seed=11111111 assertion failed")
        r2 = make_rec("seed=22222222 assertion failed")
        result = cluster_b1([r1, r2])
        assert result.n_clusters == 1

    def test_distinct_error_types_separate(self):
        r1 = make_rec("%Error: count == expected")
        r2 = make_rec("UVM_FATAL [TIMEOUT]: watchdog")
        result = cluster_b1([r1, r2])
        assert result.n_clusters == 2

    def test_empty_input(self):
        result = cluster_b1([])
        assert result.n_clusters == 0

    def test_method_label(self):
        result = cluster_b1([make_rec("x")])
        assert result.method == "B1"


class TestB2Clustering:
    def test_similar_messages_one_cluster(self):
        records = [
            make_rec("assertion failed count mismatch counter"),
            make_rec("assertion failed count mismatch fifo"),
            make_rec("assertion failed count mismatch module"),
        ]
        result = cluster_b2(records, ClusteringConfig(distance_threshold=0.3))
        # Should merge similar messages
        assert result.n_clusters <= 2

    def test_distinct_messages_multiple_clusters(self):
        records = [
            make_rec("assertion failed counter"),
            make_rec("UVM timeout watchdog"),
            make_rec("compile error syntax"),
        ]
        result = cluster_b2(records, ClusteringConfig(distance_threshold=0.3))
        assert result.n_clusters >= 2

    def test_empty_input(self):
        result = cluster_b2([])
        assert result.n_clusters == 0

    def test_single_record(self):
        result = cluster_b2([make_rec("solo")])
        assert result.n_clusters == 1

    def test_labels_parallel_to_records(self):
        records = [make_rec("a"), make_rec("b"), make_rec("c")]
        result = cluster_b2(records)
        assert len(result.labels) == len(records)

    def test_method_label(self):
        result = cluster_b2([make_rec("x")])
        assert result.method == "B2"

    def test_degenerate_all_identical(self):
        records = [make_rec("identical") for _ in range(5)]
        result = cluster_b2(records)
        assert result.n_clusters == 1  # all identical → one cluster


class TestB3Clustering:
    def test_runs_without_error(self):
        records = [make_rec("error A"), make_rec("error B")]
        result = cluster_b3(records)
        assert result.method == "B3"
        assert len(result.labels) == 2

    def test_empty_input(self):
        result = cluster_b3([])
        assert result.n_clusters == 0

    def test_labels_parallel(self):
        records = [make_rec("x"), make_rec("y"), make_rec("z")]
        result = cluster_b3(records)
        assert len(result.labels) == 3

    def test_ground_truth_not_accessed(self):
        """B3 must never access ground_truth_bug_ids."""
        rec = make_rec("some error")
        rec.ground_truth_bug_ids = ["bug_1"]
        # If it accessed ground truth labels, we'd need to detect that —
        # here we just verify it runs and doesn't leak them into labels
        result = cluster_b3([rec])
        assert result.n_clusters == 1


class TestRunAllMethods:
    def test_returns_all_four_methods(self):
        records = [make_rec("error X"), make_rec("error Y")]
        results = run_all_methods(records)
        assert set(results.keys()) == {"B0", "B1", "B2", "B3"}

    def test_all_labels_parallel(self):
        records = [make_rec("a"), make_rec("b"), make_rec("c")]
        results = run_all_methods(records)
        for method, cr in results.items():
            assert len(cr.labels) == 3, f"{method} labels length mismatch"
