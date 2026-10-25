"""Unit tests for HTML reporting module, especially security and escaping."""
import pytest
from pathlib import Path

from failscope.models import FailureRecord, ParseResult, RunMetadata
from failscope.clustering import ClusterResult
from failscope.comparison import ComparisonResult, SignatureDiff
from failscope.reporting import generate_report, _e


class TestHTMLEscaping:
    def test_escaping_function(self):
        assert _e("<script>") == "&lt;script&gt;"
        assert _e('"quotes"') == "&quot;quotes&quot;"
        assert _e("a & b") == "a &amp; b"
        assert _e(None) == ""

    def test_script_tag_in_error_message_is_escaped(self, tmp_path):
        malicious = "<script>alert('XSS')</script>"
        rec = FailureRecord(
            first_error_message=malicious,
            raw_evidence_reference="test.log:1",
        )
        pr = ParseResult(failures=[rec], metadata=RunMetadata(source_path="test.log"))
        out_file = tmp_path / "xss_report.html"
        html_out = generate_report(pr, output_path=out_file)

        assert "<script>alert('XSS')</script>" not in html_out
        assert "&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;" in html_out or "&lt;script&gt;alert('XSS')&lt;/script&gt;" in html_out

    def test_html_in_context_lines_is_escaped(self, tmp_path):
        rec = FailureRecord(
            first_error_message="normal error",
            context_lines=["<img src=x onerror=alert(1)>", "<svg/onload=alert(1)>"],
            raw_evidence_reference="test.log:1",
        )
        pr = ParseResult(failures=[rec], metadata=RunMetadata(source_path="test.log"))
        html_out = generate_report(pr, output_path=tmp_path / "context_report.html")

        assert "<img src=x onerror=alert(1)>" not in html_out
        assert "<svg/onload=alert(1)>" not in html_out


class TestReportProperties:
    def test_no_external_resources(self, tmp_path):
        rec = FailureRecord(
            first_error_message="Error: failed",
            raw_evidence_reference="test.log:1",
        )
        pr = ParseResult(failures=[rec], metadata=RunMetadata(source_path="test.log"))
        html_out = generate_report(pr, output_path=tmp_path / "offline_report.html")

        # Must not load anything from external CDNs
        assert "http://" not in html_out
        assert "https://" not in html_out
        assert "src=\"http" not in html_out
        assert "href=\"http" not in html_out

    def test_report_with_cluster_result(self, tmp_path):
        recs = [
            FailureRecord(first_error_message="Err 1", raw_evidence_reference="test.log:1"),
            FailureRecord(first_error_message="Err 2", raw_evidence_reference="test.log:2"),
        ]
        cr = ClusterResult(method="B1", labels=[0, 1], n_clusters=2, params={})
        pr = ParseResult(failures=recs, metadata=RunMetadata(source_path="test.log"))
        html_out = generate_report(pr, cluster_result=cr, output_path=tmp_path / "clustered.html")

        assert "Failure Clusters (2 groups, B1 method)" in html_out
        assert "Cluster 0" in html_out
        assert "Cluster 1" in html_out

    def test_report_with_comparison(self, tmp_path):
        pr = ParseResult(failures=[], metadata=RunMetadata(source_path="candidate.log"))
        comp = ComparisonResult(
            baseline_run_id="base",
            candidate_run_id="cand",
            baseline_source="base.log",
            candidate_source="cand.log",
            new_failures=[SignatureDiff("new_sig", 0, 2, [], ["t1", "t2"])],
            disappeared_failures=[SignatureDiff("old_sig", 1, 0, ["t0"], [])],
            persistent_failures=[SignatureDiff("same_sig", 1, 1, ["t3"], ["t3"])],
        )
        html_out = generate_report(pr, comparison=comp, output_path=tmp_path / "comp.html")
        assert "Run Comparison" in html_out
        assert "new_sig" in html_out
        assert "old_sig" in html_out
        assert "same_sig" in html_out
