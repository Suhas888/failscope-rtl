"""Unit tests for data models."""
import pytest
from failscope.models import (
    FailureRecord, FieldSource, FieldProvenance, RunMetadata, ParseResult
)


class TestFailureRecord:
    def test_default_fields_are_none(self):
        rec = FailureRecord()
        assert rec.test_name is None
        assert rec.seed is None
        assert rec.commit_sha is None
        assert rec.timestamp is None
        assert rec.ground_truth_bug_ids == []

    def test_failure_id_is_unique(self):
        r1 = FailureRecord()
        r2 = FailureRecord()
        assert r1.failure_id != r2.failure_id

    def test_provenance_tracking(self):
        rec = FailureRecord(first_error_message="test error")
        rec.set_provenance("first_error_message", FieldSource.OBSERVED)
        assert rec.provenance["first_error_message"].source == FieldSource.OBSERVED

    def test_mark_unavailable(self):
        rec = FailureRecord()
        rec.mark_unavailable("seed", "commit_sha", "timestamp")
        assert rec.provenance["seed"].source == FieldSource.UNAVAILABLE
        assert rec.provenance["commit_sha"].source == FieldSource.UNAVAILABLE
        assert rec.provenance["timestamp"].source == FieldSource.UNAVAILABLE

    def test_to_dict_excludes_ground_truth(self):
        rec = FailureRecord()
        rec.ground_truth_bug_ids = ["bug_1", "bug_2"]
        d = rec.to_dict()
        assert "ground_truth_bug_ids" not in d

    def test_to_dict_with_labels_includes_ground_truth(self):
        rec = FailureRecord()
        rec.ground_truth_bug_ids = ["bug_1"]
        d = rec.to_dict_with_labels()
        assert "ground_truth_bug_ids" in d
        assert d["ground_truth_bug_ids"] == ["bug_1"]

    def test_round_trip(self):
        rec = FailureRecord(
            test_name="test_foo",
            simulator="verilator",
            error_class="assertion",
            first_error_message="%Error: foo.v:10: Assertion failed",
            context_lines=["line1", "line2"],
            source_file="foo.v",
            source_line=10,
        )
        rec.set_provenance("first_error_message", FieldSource.OBSERVED)
        d = rec.to_dict()
        rec2 = FailureRecord.from_dict(d)
        assert rec2.test_name == rec.test_name
        assert rec2.first_error_message == rec.first_error_message
        assert rec2.context_lines == rec.context_lines
        assert rec2.provenance["first_error_message"].source == FieldSource.OBSERVED

    def test_never_invent_seed(self):
        """Seeds must remain None if not observed — never fabricated."""
        rec = FailureRecord()
        assert rec.seed is None

    def test_unicode_message(self):
        msg = "Ошибка: сигнал X в регистре — assertion failed ♦"
        rec = FailureRecord(first_error_message=msg)
        d = rec.to_dict()
        assert d["first_error_message"] == msg


class TestRunMetadata:
    def test_to_dict(self):
        meta = RunMetadata(simulator="verilator", total_tests=10, failed_tests=3)
        d = meta.to_dict()
        assert d["simulator"] == "verilator"
        assert d["total_tests"] == 10

    def test_parse_result_failure_count(self):
        meta = RunMetadata()
        pr = ParseResult(metadata=meta, failures=[FailureRecord(), FailureRecord()])
        assert pr.failure_count == 2
