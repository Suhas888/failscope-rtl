"""Unit tests for JUnit XML (cocotb) parser."""
import textwrap
import pytest
from pathlib import Path

from failscope.parsers.cocotb import parse_junit_xml


@pytest.fixture
def tmp_xml(tmp_path):
    def _write(content: str) -> Path:
        p = tmp_path / "results.xml"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p
    return _write


class TestJUnitParser:

    def test_parses_testsuites_root(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuites tests="2" failures="1">
              <testsuite name="tb" tests="2" failures="1">
                <testcase name="test_a" classname="tb">
                  <failure type="AssertionError" message="count mismatch">
                    counter.v:42: Assertion failed: count == 7
                  </failure>
                </testcase>
                <testcase name="test_b" classname="tb"/>
              </testsuite>
            </testsuites>
        """)
        result = parse_junit_xml(p)
        assert len(result.failures) == 1
        assert "test_a" in result.failures[0].test_name

    def test_parses_testsuite_root(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite name="tb" tests="1" failures="1">
              <testcase name="test_x" classname="tb">
                <failure type="Error">fail message</failure>
              </testcase>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert len(result.failures) == 1

    def test_skipped_not_counted(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite tests="1" failures="0">
              <testcase name="test_skip">
                <skipped/>
              </testcase>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert len(result.failures) == 0

    def test_passing_not_counted(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite tests="1" failures="0">
              <testcase name="test_pass"/>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert len(result.failures) == 0

    def test_error_element(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite tests="1" errors="1">
              <testcase name="test_err">
                <error type="RuntimeError">something went wrong</error>
              </testcase>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert len(result.failures) == 1

    def test_malformed_xml_produces_warning(self, tmp_xml):
        p = tmp_xml("<broken><xml>no closing tags")
        result = parse_junit_xml(p)
        assert len(result.failures) == 0
        assert result.metadata.parse_warnings

    def test_empty_file_produces_warning(self, tmp_xml):
        p = tmp_xml("")
        result = parse_junit_xml(p)
        assert len(result.failures) == 0
        assert result.metadata.parse_warnings

    def test_missing_file_produces_warning(self, tmp_path):
        p = tmp_path / "missing.xml"
        result = parse_junit_xml(p)
        assert len(result.failures) == 0
        assert any("not found" in w.lower() for w in result.metadata.parse_warnings)

    def test_multiple_testsuites(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuites>
              <testsuite name="suite1" tests="1" failures="1">
                <testcase name="t1"><failure>fail1</failure></testcase>
              </testsuite>
              <testsuite name="suite2" tests="1" failures="1">
                <testcase name="t2"><failure>fail2</failure></testcase>
              </testsuite>
            </testsuites>
        """)
        result = parse_junit_xml(p)
        assert len(result.failures) == 2

    def test_test_count_metadata(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite tests="5" failures="2" errors="0" skipped="1">
              <testcase name="t1"><failure>f</failure></testcase>
              <testcase name="t2"><failure>f</failure></testcase>
              <testcase name="t3"/>
              <testcase name="t4"/>
              <testcase name="t5"><skipped/></testcase>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert result.metadata.total_tests == 5
        assert result.metadata.failed_tests == 2

    def test_classname_included_in_test_name(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite tests="1" failures="1">
              <testcase name="test_count" classname="counter_tb">
                <failure>fail</failure>
              </testcase>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert "counter_tb" in result.failures[0].test_name

    def test_simulator_defaults_to_cocotb(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite tests="1" failures="1">
              <testcase name="t"><failure>fail</failure></testcase>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert result.metadata.simulator == "cocotb"

    def test_unicode_failure_message(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite tests="1" failures="1">
              <testcase name="t">
                <failure>Ошибка: assertion ♦</failure>
              </testcase>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert len(result.failures) == 1

    def test_warns_when_no_simulator_error_line(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite tests="1" failures="1">
              <testcase name="t">
                <failure type="AssertionError">generic test failure summary</failure>
              </testcase>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert len(result.failures) == 1
        assert any("summary" in w.lower() or "simulator" in w.lower()
                   for w in result.failures[0].parse_warnings)

    def test_never_fabricates_seed(self, tmp_xml):
        p = tmp_xml("""\
            <?xml version="1.0"?>
            <testsuite tests="1" failures="1">
              <testcase name="t"><failure>fail</failure></testcase>
            </testsuite>
        """)
        result = parse_junit_xml(p)
        assert result.failures[0].seed is None
