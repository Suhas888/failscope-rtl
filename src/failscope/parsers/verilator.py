"""
Verilator text log parser for FailScope RTL.

Recognises representative patterns from Verilator output:
  - %Error: file:line: message
  - %Fatal: file:line: message
  - %Warning-*: (captured but not counted as failures)
  - Assertion failed
  - Internal abort / terminate signals

Limitations documented:
  - Does not cover every Verilator version or build configuration.
  - Does not handle multi-language (SC) mode.
  - %Warning lines are collected as context, not failures.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from failscope.models import FailureRecord, FieldSource, ParseResult, RunMetadata

import uuid as _uuid

# --- Pattern definitions ---

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# Core error patterns
_ERROR_RE = re.compile(
    r"^(%Error(?:-\w+)?|%Fatal(?:-\w+)?)"   # prefix
    r"(?::\s*([\w./\\\-]+\.(v|sv|vh|svh)):(\d+))?"  # optional file:line
    r":\s*(.+)$",                             # message
    re.IGNORECASE,
)

# Assertion failures (e.g., from $error, $fatal)
_ASSERT_RE = re.compile(
    r"(?:Assertion failed|assert\s+failed|simulation abort)",
    re.IGNORECASE,
)

# Fatal exit
_FATAL_RE = re.compile(r"^\s*%Fatal\b", re.IGNORECASE)

# Test failure summaries (heuristic)
_SUMMARY_RE = re.compile(
    r"(?:FAIL|FAILED|TEST\s+FAILED|\*\*\s*FAILED\s*\*\*)",
    re.IGNORECASE,
)

# Simulation time
_SIMTIME_RE = re.compile(r"\bat\s+time\s+([\d.]+)\s*(\w+)", re.IGNORECASE)

# Source file mention
_SOURCE_RE = re.compile(r"([\w/\\\-.]+\.(v|sv|vh|svh)):(\d+)")

# Module mention
_MODULE_RE = re.compile(r"\b([A-Za-z_][\w]+)\s*\(")

_CONTEXT_WINDOW = 5  # lines before/after an error to capture


def _classify_error(prefix: str) -> str:
    prefix_lower = prefix.lower()
    if "fatal" in prefix_lower:
        return "fatal"
    if "error" in prefix_lower:
        return "assertion" if "assert" in prefix_lower else "error"
    return "error"


def parse_verilator_log(
    path: str | Path,
    run_id: Optional[str] = None,
) -> ParseResult:
    """
    Parse a Verilator text log file and return a ParseResult.

    Multiple failures in one log are returned as separate records.
    Gracefully handles empty files and unexpected content.
    """
    path = Path(path)
    source_path = str(path)
    run_id = run_id or str(_uuid.uuid4())

    meta = RunMetadata(
        run_id=run_id,
        simulator="verilator",
        source_path=source_path,
    )

    if not path.exists():
        meta.parse_warnings.append(f"File not found: {source_path}")
        return ParseResult(metadata=meta)

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        meta.parse_warnings.append(f"Cannot read file: {exc}")
        return ParseResult(metadata=meta)

    if not text.strip():
        meta.parse_warnings.append("Empty log file.")
        return ParseResult(metadata=meta)

    lines = text.splitlines()
    failures: list[FailureRecord] = []
    seen_messages: set[str] = set()  # for deduplication within one log

    for idx, line in enumerate(lines):
        stripped = _ANSI_RE.sub("", line).strip()

        # Match %Error / %Fatal
        m = _ERROR_RE.match(stripped)
        if m:
            prefix, src_file_raw, _ext, src_line_raw, message = m.groups()
            error_class = _classify_error(prefix)
            first_error = f"{prefix}: {message}".strip()

            # Avoid re-adding duplicate lines
            if first_error in seen_messages:
                continue
            seen_messages.add(first_error)

            src_file = src_file_raw or None
            src_line = int(src_line_raw) if src_line_raw else None

            # context window
            ctx_start = max(0, idx - _CONTEXT_WINDOW)
            ctx_end = min(len(lines), idx + _CONTEXT_WINDOW + 1)
            context = [l.rstrip() for l in lines[ctx_start:ctx_end]]

            # simulation time
            sim_time = sim_unit = None
            tm = _SIMTIME_RE.search(stripped)
            if tm:
                sim_time, sim_unit = tm.group(1), tm.group(2)

            # mentioned files/modules from context
            ctx_text = "\n".join(context)
            mentioned_files = list(dict.fromkeys(
                m2.group(1) for m2 in _SOURCE_RE.finditer(ctx_text)
            ))
            mentioned_modules = list(dict.fromkeys(
                m2.group(1) for m2 in _MODULE_RE.finditer(ctx_text)
            ))

            record = FailureRecord(
                run_id=run_id,
                simulator="verilator",
                error_class=error_class,
                first_error_message=first_error,
                context_lines=context,
                source_file=src_file,
                source_line=src_line,
                simulation_time=sim_time,
                simulation_time_unit=sim_unit,
                mentioned_files=mentioned_files,
                mentioned_modules=mentioned_modules,
                raw_evidence_reference=source_path,
            )
            record.set_provenance("first_error_message", FieldSource.OBSERVED)
            record.set_provenance("source_file",
                FieldSource.OBSERVED if src_file else FieldSource.UNAVAILABLE)
            record.set_provenance("source_line",
                FieldSource.OBSERVED if src_line else FieldSource.UNAVAILABLE)
            record.set_provenance("simulation_time",
                FieldSource.OBSERVED if sim_time else FieldSource.UNAVAILABLE)
            record.mark_unavailable("test_name", "seed", "commit_sha", "timestamp")
            failures.append(record)
            continue

        # Assertion / summary patterns that don't match %Error
        if _ASSERT_RE.search(stripped) or _SUMMARY_RE.search(stripped):
            first_error = stripped
            if first_error in seen_messages:
                continue
            seen_messages.add(first_error)

            ctx_start = max(0, idx - _CONTEXT_WINDOW)
            ctx_end = min(len(lines), idx + _CONTEXT_WINDOW + 1)
            context = [l.rstrip() for l in lines[ctx_start:ctx_end]]

            # Try to extract source from context
            src_file = src_line = None
            for cl in context:
                sm = _SOURCE_RE.search(cl)
                if sm:
                    src_file, src_line = sm.group(1), int(sm.group(3))
                    break

            record = FailureRecord(
                run_id=run_id,
                simulator="verilator",
                error_class="assertion",
                first_error_message=first_error,
                context_lines=context,
                source_file=src_file,
                source_line=src_line,
                raw_evidence_reference=source_path,
            )
            record.set_provenance("first_error_message", FieldSource.OBSERVED)
            record.set_provenance("source_file",
                FieldSource.OBSERVED if src_file else FieldSource.UNAVAILABLE)
            record.mark_unavailable("test_name", "seed", "commit_sha", "timestamp",
                                     "simulation_time")
            record.parse_warnings.append(
                "Matched as assertion/summary pattern, not %Error/%Fatal."
            )
            failures.append(record)

    if not failures:
        meta.parse_warnings.append(
            "No %Error, %Fatal, or assertion failures found in log."
        )

    meta.failed_tests = len(failures) or None
    return ParseResult(metadata=meta, failures=failures)
