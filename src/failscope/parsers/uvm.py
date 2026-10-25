"""
UVM-style text log parser for FailScope RTL.

Recognises representative UVM report patterns:
  - UVM_ERROR [report_id] (component) @ sim_time: message
  - UVM_FATAL [report_id] (component) @ sim_time: message

Does NOT attempt to parse every possible UVM configuration.
Produces parse_warnings for unrecognised patterns.

Limitations:
  - Report format varies by UVM version and user customisation.
  - This parser covers the most common textual patterns only.
  - Simulation time parsing assumes "@ NNN ns" style.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from failscope.models import FailureRecord, FieldSource, ParseResult, RunMetadata

import uuid as _uuid

# --- Pattern definitions ---

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# UVM line: UVM_ERROR [ID] component @ time: message
# Many variants; we use a flexible regex.
_UVM_LINE_RE = re.compile(
    r"(?P<severity>UVM_ERROR|UVM_FATAL)"
    r"(?:\s+\[(?P<report_id>[^\]]*)\])?"          # optional [ID]
    r"(?:\s+(?P<component>[^\@]+?))?"              # optional component
    r"(?:\s*@\s*(?P<sim_time>[\d.]+\s*\w+))?"     # optional @ time
    r"(?:\s*:\s*(?P<message>.+))?$",               # optional message
    re.IGNORECASE,
)

# Summary line: "UVM Report Summary"
_SUMMARY_RE = re.compile(r"UVM Report Summary", re.IGNORECASE)

# UVM_FATAL run summary
_FINAL_FATAL_RE = re.compile(r"UVM_FATAL\s*:\s*(\d+)", re.IGNORECASE)
_FINAL_ERROR_RE = re.compile(r"UVM_ERROR\s*:\s*(\d+)", re.IGNORECASE)

# Source file mention
_SOURCE_RE = re.compile(r"([\w/\\\-.]+\.(v|sv|vh|svh|vhd|vhdl)):(\d+)")

_CONTEXT_WINDOW = 5


def _parse_sim_time(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Split '100 ns' into ('100', 'ns')."""
    if not raw:
        return None, None
    m = re.match(r"([\d.]+)\s*(\w+)?", raw.strip())
    if m:
        return m.group(1), m.group(2) or None
    return raw.strip(), None


def parse_uvm_log(
    path: str | Path,
    run_id: Optional[str] = None,
) -> ParseResult:
    """
    Parse a UVM-style text log and return a ParseResult.

    One FailureRecord is created per UVM_ERROR / UVM_FATAL line.
    Summary counts are captured in RunMetadata.
    """
    path = Path(path)
    source_path = str(path)
    run_id = run_id or str(_uuid.uuid4())

    meta = RunMetadata(
        run_id=run_id,
        simulator="uvm",
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

    in_summary = False
    summary_error_count = summary_fatal_count = None

    for idx, line in enumerate(lines):
        stripped = _ANSI_RE.sub("", line).strip()

        # Detect summary section
        if _SUMMARY_RE.search(stripped):
            in_summary = True
            continue

        if in_summary:
            fm = _FINAL_FATAL_RE.search(stripped)
            em = _FINAL_ERROR_RE.search(stripped)
            if fm:
                summary_fatal_count = int(fm.group(1))
            if em:
                summary_error_count = int(em.group(1))
            continue

        # Match UVM_ERROR / UVM_FATAL
        m = _UVM_LINE_RE.match(stripped)
        if not m:
            continue

        severity = m.group("severity").upper()
        report_id = (m.group("report_id") or "").strip() or None
        component = (m.group("component") or "").strip() or None
        sim_time_raw = (m.group("sim_time") or "").strip() or None
        message = (m.group("message") or "").strip() or None

        sim_time, sim_unit = _parse_sim_time(sim_time_raw)

        # Build first_error_message from available parts
        parts = [severity]
        if report_id:
            parts.append(f"[{report_id}]")
        if component:
            parts.append(component)
        if message:
            parts.append(f": {message}")
        first_error = " ".join(parts)

        # Context
        ctx_start = max(0, idx - _CONTEXT_WINDOW)
        ctx_end = min(len(lines), idx + _CONTEXT_WINDOW + 1)
        context = [l.rstrip() for l in lines[ctx_start:ctx_end]]

        # Source files / modules from context
        ctx_text = "\n".join(context)
        mentioned_files = list(dict.fromkeys(
            mm.group(1) for mm in _SOURCE_RE.finditer(ctx_text)
        ))

        src_file = src_line = None
        sm = _SOURCE_RE.search(stripped)
        if sm:
            src_file, src_line = sm.group(1), int(sm.group(3))

        error_class = "fatal" if severity == "UVM_FATAL" else "uvm_error"

        record = FailureRecord(
            run_id=run_id,
            simulator="uvm",
            error_class=error_class,
            first_error_message=first_error,
            context_lines=context,
            source_file=src_file,
            source_line=src_line,
            simulation_time=sim_time,
            simulation_time_unit=sim_unit,
            mentioned_files=mentioned_files,
            mentioned_modules=[c for c in ([component] if component else []) if c],
            raw_evidence_reference=source_path,
        )
        record.set_provenance("first_error_message", FieldSource.OBSERVED)
        record.set_provenance("source_file",
            FieldSource.OBSERVED if src_file else FieldSource.UNAVAILABLE)
        record.set_provenance("simulation_time",
            FieldSource.OBSERVED if sim_time else FieldSource.UNAVAILABLE)
        record.mark_unavailable("test_name", "seed", "commit_sha", "timestamp")

        # Store report_id and component in extra metadata
        record.parse_warnings  # (already initialised)
        if report_id:
            record.mentioned_modules = list(dict.fromkeys(
                [report_id] + record.mentioned_modules
            ))

        failures.append(record)

    if not failures:
        meta.parse_warnings.append("No UVM_ERROR or UVM_FATAL lines found in log.")

    # Use summary counts if available; else use parsed record count
    if summary_error_count is not None or summary_fatal_count is not None:
        meta.failed_tests = (summary_error_count or 0) + (summary_fatal_count or 0)
    else:
        meta.failed_tests = len(failures) or None

    return ParseResult(metadata=meta, failures=failures)
