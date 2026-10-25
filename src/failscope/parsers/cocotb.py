"""
JUnit XML parser for FailScope RTL.

Supports:
  - <testsuites> and <testsuite> roots
  - <testcase> with <failure> and <error> child elements
  - <skipped> elements
  - system-out and system-err
  - testcase properties
  - Malformed / incomplete XML with graceful degradation

Important design note:
  A test failure in XML is not necessarily a distinct root cause.
  Multiple testcases can fail due to the same underlying defect.
  This parser creates one FailureRecord per failing testcase; the
  clustering stage decides which share a cause.

  XML alone often lacks the first simulator error. A parse_warning
  is added when the failure body appears to be a high-level summary
  rather than a simulator error line.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from failscope.models import FailureRecord, FieldSource, ParseResult, RunMetadata


# Patterns that suggest the failure body is a simulator error line
_SIMULATOR_ERROR_PATTERNS = [
    re.compile(r"%Error", re.IGNORECASE),
    re.compile(r"%Fatal", re.IGNORECASE),
    re.compile(r"UVM_ERROR", re.IGNORECASE),
    re.compile(r"UVM_FATAL", re.IGNORECASE),
    re.compile(r"Assertion failed", re.IGNORECASE),
    re.compile(r"ERROR:"),
    re.compile(r"FATAL:"),
]

_MENTIONED_FILE_RE = re.compile(r"([\w/.\-]+\.(v|sv|vh|svh|vhd|vhdl))")
_MENTIONED_MODULE_RE = re.compile(r"\b([A-Za-z_][\w.]*)\s*(?:\.|\[)")

_MAX_CONTEXT_LINES = 10


def _looks_like_simulator_error(text: str) -> bool:
    return any(p.search(text) for p in _SIMULATOR_ERROR_PATTERNS)


def _extract_first_error_line(text: str) -> Optional[str]:
    """Return the first line that looks like a simulator error, else first non-empty line."""
    if not text:
        return None
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        if _looks_like_simulator_error(line):
            return line
    return lines[0] if lines else None


def _extract_context(text: str, max_lines: int = _MAX_CONTEXT_LINES) -> list[str]:
    """Return up to max_lines non-empty lines from text."""
    if not text:
        return []
    return [l.rstrip() for l in text.splitlines() if l.strip()][:max_lines]


def _extract_mentioned_files(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in _MENTIONED_FILE_RE.finditer(text)))


def _extract_mentioned_modules(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in _MENTIONED_MODULE_RE.finditer(text)))


def _parse_source_location(text: str) -> tuple[Optional[str], Optional[int]]:
    """Try to extract file:line from a failure message."""
    # Patterns: "file.v:42:", "file.v(42)", "at file.v line 42"
    patterns = [
        re.compile(r"([\w/.\-]+\.(v|sv|vh|svh|vhd|vhdl)):(\d+)"),
        re.compile(r"([\w/.\-]+\.(v|sv|vh|svh|vhd|vhdl))\((\d+)\)"),
        re.compile(r"at ([\w/.\-]+\.(v|sv|vh|svh|vhd|vhdl)) line (\d+)", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(text or "")
        if m:
            return m.group(1), int(m.group(3))
    return None, None


def _parse_testcase(
    tc: ET.Element,
    suite_name: Optional[str],
    run_id: str,
    source_path: str,
    warnings: list[str],
) -> Optional[FailureRecord]:
    """Parse a single <testcase> element; return None if it passed or was skipped."""
    failure_el = tc.find("failure")
    error_el = tc.find("error")
    skipped_el = tc.find("skipped")

    if skipped_el is not None:
        return None
    if failure_el is None and error_el is None:
        return None

    el = failure_el if failure_el is not None else error_el
    assert el is not None

    # Raw text evidence
    failure_message = el.get("message", "")
    failure_type = el.get("type", "")
    failure_body = (el.text or "").strip()

    # system-out / system-err may contain simulator lines
    sys_out = (tc.findtext("system-out") or "").strip()
    sys_err = (tc.findtext("system-err") or "").strip()

    # Combine evidence for first-error extraction
    combined_text = "\n".join(filter(None, [failure_message, failure_body, sys_err, sys_out]))

    first_error = _extract_first_error_line(combined_text)
    context = _extract_context(combined_text)

    src_file, src_line = _parse_source_location(combined_text)
    mentioned_files = _extract_mentioned_files(combined_text)
    mentioned_modules = _extract_mentioned_modules(combined_text)

    tc_name = tc.get("name", "")
    classname = tc.get("classname", "")
    test_name = f"{classname}.{tc_name}" if classname else tc_name

    # Warn if the failure body doesn't look like a simulator error
    body_looks_like_summary = not _looks_like_simulator_error(combined_text)

    record = FailureRecord(
        test_name=test_name or None,
        run_id=run_id,
        simulator="cocotb",  # JUnit XML is most commonly cocotb/pytest
        error_class=failure_type or ("failure" if failure_el is not None else "error"),
        first_error_message=first_error,
        context_lines=context,
        source_file=src_file,
        source_line=src_line,
        mentioned_files=list(dict.fromkeys(mentioned_files)),
        mentioned_modules=list(dict.fromkeys(mentioned_modules)),
        raw_evidence_reference=source_path,
    )

    record.set_provenance("test_name", FieldSource.OBSERVED if test_name else FieldSource.UNAVAILABLE)
    record.set_provenance("first_error_message", FieldSource.OBSERVED if first_error else FieldSource.UNAVAILABLE)
    record.set_provenance("source_file", FieldSource.OBSERVED if src_file else FieldSource.UNAVAILABLE)
    record.mark_unavailable("seed", "commit_sha", "timestamp", "simulation_time")

    if body_looks_like_summary:
        record.parse_warnings.append(
            "Failure body does not contain a recognisable simulator error line; "
            "the first_error_message may be a high-level test summary."
        )

    return record


def parse_junit_xml(
    path: str | Path,
    run_id: Optional[str] = None,
) -> ParseResult:
    """
    Parse a JUnit XML file and return a ParseResult.

    Gracefully handles malformed XML, empty files, and unexpected structure.
    """
    path = Path(path)
    source_path = str(path)
    import uuid as _uuid
    run_id = run_id or str(_uuid.uuid4())

    meta = RunMetadata(
        run_id=run_id,
        simulator="cocotb",
        source_path=source_path,
    )

    if not path.exists():
        meta.parse_warnings.append(f"File not found: {source_path}")
        return ParseResult(metadata=meta)

    try:
        raw = path.read_bytes()
        if not raw.strip():
            meta.parse_warnings.append("Empty file.")
            return ParseResult(metadata=meta)
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        meta.parse_warnings.append(f"XML parse error: {exc}. Attempting partial recovery.")
        # Try to extract raw text for any partial content
        try:
            raw_str = raw.decode("utf-8", errors="replace")
            # count failure/error mentions as a rough count
            err_count = raw_str.lower().count("<failure") + raw_str.lower().count("<error")
            if err_count:
                meta.parse_warnings.append(
                    f"Found {err_count} failure/error tag(s) in malformed XML; could not parse."
                )
        except Exception:
            pass
        return ParseResult(metadata=meta)

    # Accept both <testsuites> and <testsuite> as root
    if root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
    elif root.tag == "testsuite":
        suites = [root]
    else:
        meta.parse_warnings.append(
            f"Unexpected root element <{root.tag}>; expected <testsuites> or <testsuite>."
        )
        # Still try nested testcases
        suites = [root]

    failures: list[FailureRecord] = []
    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0

    for suite in suites:
        suite_name = suite.get("name")
        suite_tests = int(suite.get("tests", 0) or 0)
        suite_failures = int(suite.get("failures", 0) or 0)
        suite_errors = int(suite.get("errors", 0) or 0)
        suite_skipped = int(suite.get("skipped", suite.get("skip", 0)) or 0)

        total_tests += suite_tests
        total_failures += suite_failures
        total_errors += suite_errors
        total_skipped += suite_skipped

        for tc in suite.findall("testcase"):
            try:
                record = _parse_testcase(tc, suite_name, run_id, source_path, meta.parse_warnings)
                if record is not None:
                    failures.append(record)
            except Exception as exc:
                meta.parse_warnings.append(f"Error parsing testcase: {exc}")

    meta.total_tests = total_tests or None
    meta.failed_tests = (total_failures + total_errors) or None
    meta.skipped_tests = total_skipped or None
    meta.passed_tests = (
        (total_tests - total_failures - total_errors - total_skipped)
        if total_tests
        else None
    )

    return ParseResult(metadata=meta, failures=failures)
