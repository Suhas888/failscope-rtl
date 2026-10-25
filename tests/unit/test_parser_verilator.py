"""Unit tests for Verilator parser."""
import textwrap
import pytest
from pathlib import Path

from failscope.parsers.verilator import parse_verilator_log


@pytest.fixture
def tmp_log(tmp_path):
    """Helper to write a temp log file and return its path."""
    def _write(content: str) -> Path:
        p = tmp_path / "test.log"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p
    return _write


class TestVerilatorParser:

    def test_parses_error_with_location(self, tmp_log):
        p = tmp_log("""\
            %Error: counter.v:42: Assertion failed: count == expected
        """)
        result = parse_verilator_log(p)
        assert len(result.failures) == 1
        rec = result.failures[0]
        assert rec.error_class == "error"
        assert "assertion" in rec.first_error_message.lower() or "counter.v:42" in rec.first_error_message
        assert rec.source_file == "counter.v"
        assert rec.source_line == 42

    def test_parses_fatal(self, tmp_log):
        p = tmp_log("%Fatal: fifo.v:10: Internal error\n")
        result = parse_verilator_log(p)
        assert len(result.failures) == 1
        assert result.failures[0].error_class == "fatal"

    def test_parses_multiple_errors(self, tmp_log):
        p = tmp_log("""\
            %Error: a.v:1: Error one
            %Error: b.v:2: Error two
            %Error: c.v:3: Error three
        """)
        result = parse_verilator_log(p)
        assert len(result.failures) == 3

    def test_deduplicates_identical_lines(self, tmp_log):
        p = tmp_log("""\
            %Error: counter.v:42: Assertion failed: count == expected
            %Error: counter.v:42: Assertion failed: count == expected
        """)
        result = parse_verilator_log(p)
        assert len(result.failures) == 1

    def test_assertion_pattern(self, tmp_log):
        p = tmp_log("Assertion failed at counter.sv:100\n")
        result = parse_verilator_log(p)
        assert len(result.failures) == 1
        assert result.failures[0].error_class == "assertion"

    def test_empty_log_produces_warning(self, tmp_log):
        p = tmp_log("")
        result = parse_verilator_log(p)
        assert len(result.failures) == 0
        assert result.metadata.parse_warnings

    def test_no_errors_produces_warning(self, tmp_log):
        p = tmp_log("This is just info text with no errors.\n")
        result = parse_verilator_log(p)
        assert len(result.failures) == 0
        assert result.metadata.parse_warnings

    def test_missing_file_produces_warning(self, tmp_path):
        p = tmp_path / "nonexistent.log"
        result = parse_verilator_log(p)
        assert len(result.failures) == 0
        assert any("not found" in w.lower() for w in result.metadata.parse_warnings)

    def test_very_long_line(self, tmp_log):
        long_msg = "X" * 10000
        p = tmp_log(f"%Error: big.v:1: {long_msg}\n")
        result = parse_verilator_log(p)
        assert len(result.failures) == 1

    def test_unicode_message(self, tmp_log):
        p = tmp_log("%Error: unicode.v:1: Ошибка ♦\n")
        result = parse_verilator_log(p)
        assert len(result.failures) == 1
        assert "Ошибка" in result.failures[0].first_error_message

    def test_context_captured(self, tmp_log):
        p = tmp_log("""\
            Running test...
            Simulation start
            %Error: counter.v:42: Assertion failed
            Test complete
        """)
        result = parse_verilator_log(p)
        assert len(result.failures) == 1
        assert len(result.failures[0].context_lines) > 1

    def test_simulator_set_to_verilator(self, tmp_log):
        p = tmp_log("%Error: a.v:1: Error\n")
        result = parse_verilator_log(p)
        assert result.metadata.simulator == "verilator"
        assert result.failures[0].simulator == "verilator"

    def test_raw_evidence_reference_set(self, tmp_log):
        p = tmp_log("%Error: a.v:1: Error\n")
        result = parse_verilator_log(p)
        assert result.failures[0].raw_evidence_reference == str(p)

    def test_never_fabricates_seed(self, tmp_log):
        p = tmp_log("%Error: a.v:1: Error\n")
        result = parse_verilator_log(p)
        assert result.failures[0].seed is None

    def test_never_fabricates_commit(self, tmp_log):
        p = tmp_log("%Error: a.v:1: Error\n")
        result = parse_verilator_log(p)
        assert result.failures[0].commit_sha is None

    def test_ansi_color_codes_stripped(self, tmp_log):
        p = tmp_log("\x1b[31m%Error: counter.v:42: Assertion failed\x1b[0m\n")
        result = parse_verilator_log(p)
        assert len(result.failures) == 1
        assert result.failures[0].source_file == "counter.v"
        assert result.failures[0].source_line == 42
        assert "Assertion failed" in result.failures[0].first_error_message

