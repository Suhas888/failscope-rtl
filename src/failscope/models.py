"""
Canonical failure record data model for FailScope RTL.

All fields use None for genuinely unavailable values.
Fields are never fabricated — seeds, source locations, sim times,
commit SHAs, and test names must come from parsed evidence only.

Benchmark labels (ground_truth_bug_ids) are kept strictly separate
from any features used by clustering methods.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class FieldSource(str, Enum):
    """How a field value was obtained."""
    OBSERVED = "observed"       # directly extracted from log/XML
    INFERRED = "inferred"       # derived from other observed fields
    UNAVAILABLE = "unavailable" # not present in the input


@dataclass
class FieldProvenance:
    """Tracks how each field was populated."""
    source: FieldSource
    note: Optional[str] = None


@dataclass
class FailureRecord:
    """
    Canonical representation of one observed simulation failure.

    Raw evidence is preserved separately from normalised text.
    Ground-truth benchmark labels are never exposed to clustering.
    """

    # --- Identity ---
    failure_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    test_name: Optional[str] = None
    seed: Optional[str] = None          # string to preserve original format
    run_id: Optional[str] = None
    commit_sha: Optional[str] = None
    timestamp: Optional[datetime] = None
    simulator: Optional[str] = None     # e.g. "verilator", "cocotb", "uvm"

    # --- Classification ---
    error_class: Optional[str] = None           # e.g. "assertion", "fatal", "uvm_error"
    first_error_message: Optional[str] = None   # raw first error line
    normalized_signature: Optional[str] = None  # after B1 normalization

    # --- Evidence ---
    context_lines: list[str] = field(default_factory=list)  # nearby log lines
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    simulation_time: Optional[str] = None       # preserve original unit/format
    simulation_time_unit: Optional[str] = None
    mentioned_files: list[str] = field(default_factory=list)
    mentioned_modules: list[str] = field(default_factory=list)
    exit_code: Optional[int] = None

    # --- Parser diagnostics ---
    parse_warnings: list[str] = field(default_factory=list)

    # --- Raw evidence ---
    raw_evidence_reference: Optional[str] = None  # path to source log/XML

    # --- Benchmark-only field (NEVER used as a clustering feature) ---
    ground_truth_bug_ids: list[str] = field(default_factory=list)

    # --- Provenance map ---
    # Maps field name -> FieldProvenance for key fields
    provenance: dict[str, FieldProvenance] = field(default_factory=dict)

    def set_provenance(self, field_name: str, source: FieldSource, note: Optional[str] = None) -> None:
        """Record how a field was obtained."""
        self.provenance[field_name] = FieldProvenance(source=source, note=note)

    def mark_unavailable(self, *field_names: str) -> None:
        """Mark multiple fields as unavailable."""
        for name in field_names:
            self.set_provenance(name, FieldSource.UNAVAILABLE)

    def to_dict(self) -> dict:
        """Serialise to a plain dictionary (excludes ground_truth_bug_ids)."""
        return {
            "failure_id": self.failure_id,
            "test_name": self.test_name,
            "seed": self.seed,
            "run_id": self.run_id,
            "commit_sha": self.commit_sha,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "simulator": self.simulator,
            "error_class": self.error_class,
            "first_error_message": self.first_error_message,
            "normalized_signature": self.normalized_signature,
            "context_lines": self.context_lines,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "simulation_time": self.simulation_time,
            "simulation_time_unit": self.simulation_time_unit,
            "mentioned_files": self.mentioned_files,
            "mentioned_modules": self.mentioned_modules,
            "exit_code": self.exit_code,
            "parse_warnings": self.parse_warnings,
            "raw_evidence_reference": self.raw_evidence_reference,
            "provenance": {
                k: {"source": v.source.value, "note": v.note}
                for k, v in self.provenance.items()
            },
        }

    def to_dict_with_labels(self) -> dict:
        """Serialise including ground-truth labels (benchmark use only)."""
        d = self.to_dict()
        d["ground_truth_bug_ids"] = list(self.ground_truth_bug_ids)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FailureRecord":
        """Deserialise from a plain dictionary."""
        from datetime import datetime as _dt

        ts = data.get("timestamp")
        record = cls(
            failure_id=data.get("failure_id", str(uuid.uuid4())),
            test_name=data.get("test_name"),
            seed=data.get("seed"),
            run_id=data.get("run_id"),
            commit_sha=data.get("commit_sha"),
            timestamp=_dt.fromisoformat(ts) if ts else None,
            simulator=data.get("simulator"),
            error_class=data.get("error_class"),
            first_error_message=data.get("first_error_message"),
            normalized_signature=data.get("normalized_signature"),
            context_lines=data.get("context_lines", []),
            source_file=data.get("source_file"),
            source_line=data.get("source_line"),
            simulation_time=data.get("simulation_time"),
            simulation_time_unit=data.get("simulation_time_unit"),
            mentioned_files=data.get("mentioned_files", []),
            mentioned_modules=data.get("mentioned_modules", []),
            exit_code=data.get("exit_code"),
            parse_warnings=data.get("parse_warnings", []),
            raw_evidence_reference=data.get("raw_evidence_reference"),
            ground_truth_bug_ids=data.get("ground_truth_bug_ids", []),
        )
        for k, v in data.get("provenance", {}).items():
            record.provenance[k] = FieldProvenance(
                source=FieldSource(v["source"]),
                note=v.get("note"),
            )
        return record


@dataclass
class RunMetadata:
    """Metadata for a single regression run."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    simulator: Optional[str] = None
    commit_sha: Optional[str] = None
    timestamp: Optional[datetime] = None
    total_tests: Optional[int] = None
    failed_tests: Optional[int] = None
    passed_tests: Optional[int] = None
    skipped_tests: Optional[int] = None
    source_path: Optional[str] = None
    parse_warnings: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "simulator": self.simulator,
            "commit_sha": self.commit_sha,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "total_tests": self.total_tests,
            "failed_tests": self.failed_tests,
            "passed_tests": self.passed_tests,
            "skipped_tests": self.skipped_tests,
            "source_path": self.source_path,
            "parse_warnings": self.parse_warnings,
            "extra": self.extra,
        }


@dataclass
class ParseResult:
    """Output of a parser: metadata + list of failure records."""
    metadata: RunMetadata
    failures: list[FailureRecord] = field(default_factory=list)

    @property
    def failure_count(self) -> int:
        return len(self.failures)
