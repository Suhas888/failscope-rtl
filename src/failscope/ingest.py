"""
Ingest module: format detection and parser dispatch for FailScope RTL.

Provides a single entry point that detects the log format and
invokes the appropriate parser.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from failscope.models import ParseResult, RunMetadata
from failscope.parsers.cocotb import parse_junit_xml
from failscope.parsers.verilator import parse_verilator_log
from failscope.parsers.uvm import parse_uvm_log


SUPPORTED_FORMATS = ("junit_xml", "verilator", "uvm", "auto")


def detect_format(path: Path) -> str:
    """
    Heuristically detect the log format.

    Returns one of: 'junit_xml', 'verilator', 'uvm', 'unknown'.
    """
    suffix = path.suffix.lower()
    if suffix in (".xml",):
        return "junit_xml"

    try:
        # Read first 4 KB for detection
        sample = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return "unknown"

    if re.search(r"<testsuites|<testsuite|<testcase", sample, re.IGNORECASE):
        return "junit_xml"
    if re.search(r"UVM_ERROR|UVM_FATAL", sample):
        return "uvm"
    if re.search(r"%Error|%Fatal|%Warning", sample, re.IGNORECASE):
        return "verilator"

    return "unknown"


def ingest(
    path: str | Path,
    fmt: Optional[str] = None,
    run_id: Optional[str] = None,
) -> ParseResult:
    """
    Parse a file and return a ParseResult.

    Parameters
    ----------
    path : str | Path
        Path to the input file (log or XML).
    fmt : str, optional
        Explicit format override. One of SUPPORTED_FORMATS.
        If None or 'auto', format is detected heuristically.
    run_id : str, optional
        Caller-supplied run identifier.

    Returns
    -------
    ParseResult
        Parsed metadata and failure records.
    """
    path = Path(path)
    fmt = (fmt or "auto").lower()

    if fmt == "auto":
        fmt = detect_format(path)

    if fmt == "junit_xml":
        return parse_junit_xml(path, run_id=run_id)
    elif fmt == "verilator":
        return parse_verilator_log(path, run_id=run_id)
    elif fmt == "uvm":
        return parse_uvm_log(path, run_id=run_id)
    else:
        meta = RunMetadata(source_path=str(path))
        meta.parse_warnings.append(
            f"Unknown format '{fmt}'. Supported: {', '.join(SUPPORTED_FORMATS)}. "
            "No failures extracted."
        )
        return ParseResult(metadata=meta)


def ingest_directory(
    directory: str | Path,
    fmt: Optional[str] = None,
    run_id: Optional[str] = None,
) -> list[ParseResult]:
    """
    Parse all recognised files in a directory.

    Returns a list of ParseResult objects.
    """
    directory = Path(directory)
    results = []
    extensions = (".xml", ".log", ".txt")
    for p in sorted(directory.rglob("*")):
        if p.is_file() and p.suffix.lower() in extensions:
            results.append(ingest(p, fmt=fmt, run_id=run_id))
    if not results:
        meta = RunMetadata(source_path=str(directory))
        meta.parse_warnings.append(f"No recognised files found in {directory}")
        results.append(ParseResult(metadata=meta))
    return results
