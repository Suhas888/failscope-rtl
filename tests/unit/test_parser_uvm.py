"""Unit tests for UVM parser."""
import textwrap
import pytest
from pathlib import Path

from failscope.parsers.uvm import parse_uvm_log


@pytest.fixture
def tmp_log(tmp_path):
    def _write(content: str) -> Path:
        p = tmp_path / "sim.log"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p
    return _write


class TestUVMParser:

    def test_parses_uvm_error(self, tmp_log):
        p = tmp_log("UVM_ERROR [SCB] scoreboard @ 1000ns: data mismatch\n")
        result = parse_uvm_log(p)
        assert len(result.failures) == 1
        rec = result.failures[0]
        assert rec.error_class == "uvm_error"
        assert "UVM_ERROR" in rec.first_error_message

    def test_parses_uvm_fatal(self, tmp_log):
        p = tmp_log("UVM_FATAL [TIMEOUT] tb @ 5000ns: watchdog expired\n")
        result = parse_uvm_log(p)
        assert len(result.failures) == 1
        assert result.failures[0].error_class == "fatal"

    def test_parses_multiple_errors(self, tmp_log):
        p = tmp_log("""\
            UVM_ERROR [A] comp1 @ 100ns: error one
            UVM_ERROR [B] comp2 @ 200ns: error two
            UVM_FATAL [T] tb @ 500ns: fatal
        """)
        result = parse_uvm_log(p)
        assert len(result.failures) == 3

    def test_sim_time_extracted(self, tmp_log):
        p = tmp_log("UVM_ERROR [SCB] scoreboard @ 1234ns: mismatch\n")
        result = parse_uvm_log(p)
        assert result.failures[0].simulation_time == "1234"
        assert result.failures[0].simulation_time_unit == "ns"

    def test_summary_counts_captured(self, tmp_log):
        p = tmp_log("""\
            UVM_ERROR [A] c @ 100ns: err
            UVM Report Summary
            UVM_FATAL : 0
            UVM_ERROR : 1
            UVM_WARNING : 0
        """)
        result = parse_uvm_log(p)
        assert result.metadata.failed_tests == 1

    def test_empty_log_produces_warning(self, tmp_log):
        p = tmp_log("")
        result = parse_uvm_log(p)
        assert len(result.failures) == 0
        assert result.metadata.parse_warnings

    def test_no_uvm_lines_produces_warning(self, tmp_log):
        p = tmp_log("INFO: simulation complete\n")
        result = parse_uvm_log(p)
        assert len(result.failures) == 0
        assert result.metadata.parse_warnings

    def test_missing_file(self, tmp_path):
        p = tmp_path / "nope.log"
        result = parse_uvm_log(p)
        assert len(result.failures) == 0
        assert any("not found" in w.lower() for w in result.metadata.parse_warnings)

    def test_simulator_set_to_uvm(self, tmp_log):
        p = tmp_log("UVM_ERROR [X] c @ 1ns: e\n")
        result = parse_uvm_log(p)
        assert result.metadata.simulator == "uvm"

    def test_never_fabricates_seed(self, tmp_log):
        p = tmp_log("UVM_ERROR [X] c @ 1ns: e\n")
        result = parse_uvm_log(p)
        assert result.failures[0].seed is None

    def test_context_captured(self, tmp_log):
        p = tmp_log("""\
            Simulation starting...
            Setting up environment...
            UVM_ERROR [SCB] scoreboard @ 100ns: mismatch
            Test complete
        """)
        result = parse_uvm_log(p)
        assert len(result.failures[0].context_lines) > 1

    def test_unicode_message(self, tmp_log):
        p = tmp_log("UVM_ERROR [X] comp @ 1ns: Ошибка ♦\n")
        result = parse_uvm_log(p)
        assert len(result.failures) == 1

    def test_ansi_color_codes_stripped(self, tmp_log):
        p = tmp_log("\x1b[31mUVM_ERROR [SCB] scoreboard @ 1000ns: data mismatch\x1b[0m\n")
        result = parse_uvm_log(p)
        assert len(result.failures) == 1
        assert result.failures[0].error_class == "uvm_error"
        assert "UVM_ERROR" in result.failures[0].first_error_message
