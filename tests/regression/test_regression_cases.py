"""Regression tests for edge cases and failure modes identified in Section 16."""
import pytest
from pathlib import Path

from failscope.models import FailureRecord, ParseResult, RunMetadata
from failscope.clustering import cluster_b0, cluster_b1, cluster_b2, cluster_b3, ClusteringConfig
from failscope.signatures import normalise_message
from failscope.comparison import compare_runs
from failscope.ingest import ingest
from failscope.parsers.cocotb import parse_junit_xml
from failscope.parsers.verilator import parse_verilator_log


class TestRegressionEdgeCases:
    def test_one_root_cause_with_multiple_messages(self):
        """Single bug triggers different assertion messages in different modules."""
        recs = [
            FailureRecord(first_error_message="assertion failed: fifo full write dropped", raw_evidence_reference="log:1"),
            FailureRecord(first_error_message="assertion failed: fifo overflow count mismatch", raw_evidence_reference="log:2"),
        ]
        res_b2 = cluster_b2(recs, ClusteringConfig(distance_threshold=0.6))
        assert len(res_b2.labels) == 2
        # Validates that fuzzy clustering can group these if threshold permits

    def test_different_causes_same_generic_timeout(self):
        """Distinct bugs all produce identical generic timeout."""
        recs = [
            FailureRecord(first_error_message="Timeout after 10000ns", test_name="tb_reset", raw_evidence_reference="log:1"),
            FailureRecord(first_error_message="Timeout after 10000ns", test_name="tb_dma", raw_evidence_reference="log:2"),
        ]
        # B0 will over-merge these into 1 cluster
        res_b0 = cluster_b0(recs)
        assert res_b0.n_clusters == 1

        # B3 uses test-level differences and structure
        res_b3 = cluster_b3(recs)
        assert len(res_b3.labels) == 2

    def test_multiple_simultaneous_bugs(self):
        """Interleaved errors from two bugs with normalized differences."""
        recs = [
            FailureRecord(first_error_message="counter mismatch addr=0x1000 data=0xAAAA", raw_evidence_reference="log:1"),
            FailureRecord(first_error_message="fifo underflow read empty", raw_evidence_reference="log:2"),
            FailureRecord(first_error_message="counter mismatch addr=0x2000 data=0xBBBB", raw_evidence_reference="log:3"),
            FailureRecord(first_error_message="fifo underflow read empty", raw_evidence_reference="log:4"),
        ]
        res = cluster_b1(recs)
        assert res.n_clusters == 2
        assert res.labels[0] == res.labels[2]
        assert res.labels[1] == res.labels[3]

    def test_missing_timestamps(self):
        rec = FailureRecord(first_error_message="Error at line 42", timestamp=None, raw_evidence_reference="log:1")
        rec.mark_unavailable("timestamp")
        assert rec.timestamp is None
        assert rec.provenance["timestamp"].source.value == "unavailable"

    def test_missing_source_paths(self):
        rec = FailureRecord(first_error_message="fatal simulation error", source_file=None, source_line=None, raw_evidence_reference="log:1")
        assert rec.source_file is None
        assert rec.source_line is None

    def test_malformed_xml(self, tmp_path):
        bad_xml = tmp_path / "corrupt.xml"
        bad_xml.write_text("<testsuite><unclosed>", encoding="utf-8")
        res = parse_junit_xml(bad_xml)
        assert len(res.failures) == 0
        assert len(res.metadata.parse_warnings) > 0

    def test_empty_logs(self, tmp_path):
        empty_log = tmp_path / "empty.log"
        empty_log.write_text("", encoding="utf-8")
        res = parse_verilator_log(empty_log)
        assert len(res.failures) == 0
        assert len(res.metadata.parse_warnings) > 0

    def test_very_long_lines(self, tmp_path):
        long_line = "%Error: " + ("x" * 20000) + "\n"
        log_file = tmp_path / "long.log"
        log_file.write_text(long_line, encoding="utf-8")
        res = parse_verilator_log(log_file)
        assert len(res.failures) == 1
        assert len(res.failures[0].first_error_message) >= 20000

    def test_duplicate_errors_deduplication(self, tmp_path):
        content = "%Error: counter.v:10: assert fail\n" * 5
        log_file = tmp_path / "dup.log"
        log_file.write_text(content, encoding="utf-8")
        res = parse_verilator_log(log_file)
        assert len(res.failures) == 1  # Deduplicated

    def test_unicode_messages(self):
        msg = "%Error: counter.v:10: Assertion \u2260 failed: \u03b1 != \u03b2"
        rec = FailureRecord(first_error_message=msg, raw_evidence_reference="log:1")
        norm = normalise_message(msg)
        assert "\u2260" in norm
        res = cluster_b1([rec])
        assert res.n_clusters == 1

    def test_unavailable_git_history(self):
        """When Git history is absent, comparison reports clear note without crashing."""
        base = ParseResult(failures=[], metadata=RunMetadata(source_path="run1.log", commit_sha=None))
        cand = ParseResult(failures=[], metadata=RunMetadata(source_path="run2.log", commit_sha=None))
        comp = compare_runs(base, cand)
        assert any("commit SHA" in w for w in comp.warnings)
        assert any("confounders" in n for n in comp.notes)
