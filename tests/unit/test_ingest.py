"""Unit tests for format detection and ingest dispatch."""
import pytest
from pathlib import Path

from failscope.ingest import detect_format, ingest, ingest_directory


class TestIngest:
    def test_detect_format_by_extension(self, tmp_path):
        xml_file = tmp_path / "results.xml"
        xml_file.write_text("<root/>", encoding="utf-8")
        assert detect_format(xml_file) == "junit_xml"

    def test_detect_format_verilator(self, tmp_path):
        log_file = tmp_path / "sim.log"
        log_file.write_text("%Error: counter.v:10: assertion failed\n", encoding="utf-8")
        assert detect_format(log_file) == "verilator"

    def test_detect_format_uvm(self, tmp_path):
        log_file = tmp_path / "uvm.log"
        log_file.write_text("UVM_ERROR [SCOREBOARD] mismatch\n", encoding="utf-8")
        assert detect_format(log_file) == "uvm"

    def test_detect_format_unknown(self, tmp_path):
        log_file = tmp_path / "plain.txt"
        log_file.write_text("Simulation finished cleanly without error\n", encoding="utf-8")
        assert detect_format(log_file) == "unknown"

    def test_ingest_auto_dispatch(self, tmp_path):
        log_file = tmp_path / "verilator.log"
        log_file.write_text("%Error: tb.v:5: test failed\n", encoding="utf-8")
        res = ingest(log_file)
        assert res.metadata.simulator == "verilator"
        assert len(res.failures) == 1

    def test_ingest_explicit_format(self, tmp_path):
        log_file = tmp_path / "custom.log"
        log_file.write_text("UVM_ERROR [ID] msg\n", encoding="utf-8")
        res = ingest(log_file, fmt="uvm")
        assert res.metadata.simulator == "uvm"
        assert len(res.failures) == 1

    def test_ingest_unknown_format_warning(self, tmp_path):
        log_file = tmp_path / "weird.bin"
        log_file.write_text("random binary garbage", encoding="utf-8")
        res = ingest(log_file, fmt="unknown")
        assert len(res.failures) == 0
        assert any("Unknown format" in w for w in res.metadata.parse_warnings)

    def test_ingest_directory(self, tmp_path):
        f1 = tmp_path / "run1.xml"
        f1.write_text("<testsuite tests='1' failures='1'><testcase name='t1'><failure message='fail'/></testcase></testsuite>", encoding="utf-8")
        f2 = tmp_path / "run2.log"
        f2.write_text("%Error: error\n", encoding="utf-8")
        results = ingest_directory(tmp_path)
        assert len(results) == 2
