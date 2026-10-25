"""Unit tests for run comparison module."""
import pytest
from failscope.models import FailureRecord, ParseResult, RunMetadata
from failscope.comparison import compare_runs, SignatureDiff, TestStatusChange


class TestRunComparison:
    def test_compare_new_and_disappeared(self):
        rec_base = FailureRecord(
            test_name="test_old",
            first_error_message="old error line",
            normalized_signature="old_signature",
            raw_evidence_reference="base.log:1",
        )
        rec_cand = FailureRecord(
            test_name="test_new",
            first_error_message="new error line",
            normalized_signature="new_signature",
            raw_evidence_reference="cand.log:1",
        )
        base = ParseResult(failures=[rec_base], metadata=RunMetadata(source_path="base.log"))
        cand = ParseResult(failures=[rec_cand], metadata=RunMetadata(source_path="cand.log"))

        res = compare_runs(base, cand)
        assert len(res.new_failures) == 1
        assert res.new_failures[0].signature == "new_signature"
        assert res.new_failures[0].candidate_count == 1

        assert len(res.disappeared_failures) == 1
        assert res.disappeared_failures[0].signature == "old_signature"
        assert res.disappeared_failures[0].baseline_count == 1

        assert len(res.persistent_failures) == 0

    def test_compare_persistent(self):
        rec1 = FailureRecord(
            test_name="test_common",
            normalized_signature="shared_sig",
            raw_evidence_reference="base.log:1",
        )
        rec2 = FailureRecord(
            test_name="test_common",
            normalized_signature="shared_sig",
            raw_evidence_reference="cand.log:1",
        )
        base = ParseResult(failures=[rec1], metadata=RunMetadata(source_path="base.log"))
        cand = ParseResult(failures=[rec2], metadata=RunMetadata(source_path="cand.log"))

        res = compare_runs(base, cand)
        assert len(res.new_failures) == 0
        assert len(res.disappeared_failures) == 0
        assert len(res.persistent_failures) == 1
        assert res.persistent_failures[0].signature == "shared_sig"

    def test_test_status_changes(self):
        rec_pass_to_fail = FailureRecord(
            test_name="test_regressed",
            first_error_message="assertion failed",
            raw_evidence_reference="cand.log:1",
        )
        rec_fail_to_pass = FailureRecord(
            test_name="test_fixed",
            first_error_message="old assertion",
            raw_evidence_reference="base.log:1",
        )
        base = ParseResult(failures=[rec_fail_to_pass], metadata=RunMetadata(source_path="base.log"))
        cand = ParseResult(failures=[rec_pass_to_fail], metadata=RunMetadata(source_path="cand.log"))

        res = compare_runs(base, cand)
        changes = {c.test_name: c.change for c in res.test_changes}
        assert changes["test_fixed"] == "fail_to_pass"
        assert changes["test_regressed"] == "pass_to_fail"

    def test_warning_on_missing_commit_sha(self):
        base = ParseResult(failures=[], metadata=RunMetadata(source_path="base.log", commit_sha=None))
        cand = ParseResult(failures=[], metadata=RunMetadata(source_path="cand.log", commit_sha=None))
        res = compare_runs(base, cand)
        assert any("commit SHA" in w for w in res.warnings)

    def test_empty_runs(self):
        base = ParseResult(failures=[], metadata=RunMetadata(source_path="base.log"))
        cand = ParseResult(failures=[], metadata=RunMetadata(source_path="cand.log"))
        res = compare_runs(base, cand)
        assert len(res.new_failures) == 0
        assert len(res.disappeared_failures) == 0
        assert len(res.persistent_failures) == 0
        assert "New: 0 | Disappeared: 0 | Persistent: 0" in res.summary()
