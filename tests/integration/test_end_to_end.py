"""Integration tests for FailScope RTL end-to-end workflows."""
import json
import subprocess
import sys
from pathlib import Path
import pytest

from failscope.ingest import ingest
from failscope.clustering import run_all_methods, cluster_b1
from failscope.reporting import generate_report
from failscope.comparison import compare_runs
from failscope.benchmark.scenarios import generate_scenarios
from failscope.benchmark.runner import run_benchmark


class TestIntegrationWorkflow:
    def test_parse_fixture_and_generate_html_report(self, tmp_path):
        """Integration: parse representative fixture log and produce HTML report."""
        fixture_path = Path(__file__).parent.parent.parent / "examples" / "logs" / "verilator_example.log"
        assert fixture_path.exists(), f"Fixture missing: {fixture_path}"

        parse_result = ingest(fixture_path)
        assert len(parse_result.failures) == 3

        cluster_result = cluster_b1(parse_result.failures)
        assert cluster_result.n_clusters >= 1

        out_html = tmp_path / "integration_report.html"
        html_content = generate_report(parse_result, cluster_result=cluster_result, output_path=out_html)

        assert out_html.exists()
        assert "<title>FailScope RTL Report</title>" in html_content
        assert "Assertion failed: count == expected_count" in html_content

    def test_import_two_runs_and_compare(self, tmp_path):
        """Integration: parse two distinct runs, compare them, and generate compare report."""
        base_fixture = Path(__file__).parent.parent.parent / "examples" / "logs" / "verilator_example.log"
        cand_fixture = Path(__file__).parent.parent.parent / "examples" / "logs" / "uvm_example.log"

        base_res = ingest(base_fixture)
        cand_res = ingest(cand_fixture)

        comparison = compare_runs(base_res, cand_res)
        assert len(comparison.new_failures) > 0
        assert len(comparison.disappeared_failures) > 0

        out_html = tmp_path / "integration_compare.html"
        html_content = generate_report(cand_res, comparison=comparison, output_path=out_html)
        assert out_html.exists()
        assert "Run Comparison" in html_content

    def test_synthetic_benchmark_end_to_end(self, tmp_path):
        """Integration: run synthetic benchmark and export results."""
        out_dir = tmp_path / "bench_out"
        results = run_benchmark(output_dir=out_dir, seed=123, target_count=55)

        assert "aggregates" in results
        assert "B0" in results["aggregates"]
        assert "B1" in results["aggregates"]
        assert "B2" in results["aggregates"]
        assert "B3" in results["aggregates"]

        assert (out_dir / "summary.json").exists()
        with open(out_dir / "summary.json", encoding="utf-8") as f:
            data = json.load(f)
            assert data["scenario_count"] == 55
            assert "B1" in data["methods"]
            assert "B3" in data["methods"]

    def test_cli_subprocess_execution(self, tmp_path):
        """Integration: execute CLI entry point via subprocess."""
        fixture = Path(__file__).parent.parent.parent / "examples" / "logs" / "junit_example.xml"
        report_file = tmp_path / "cli_report.html"

        # Test CLI analyze
        cmd = [
            sys.executable,
            "-m",
            "failscope.cli",
            "analyze",
            str(fixture),
            "--out",
            str(report_file),
            "--force",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0, f"CLI error: {proc.stderr}"
        assert report_file.exists()
        assert "Report written:" in proc.stdout

        # Test CLI version
        ver_proc = subprocess.run([sys.executable, "-m", "failscope.cli", "version"],
                                  capture_output=True, text=True)
        assert ver_proc.returncode == 0
        assert "FailScope RTL 0.1.0" in ver_proc.stdout
