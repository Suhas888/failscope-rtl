"""
Run comparison module for FailScope RTL.

Compares two ParseResult objects (baseline vs. candidate) and
produces a structured comparison report.

Language: uses "newly observed failure" rather than "confirmed regression cause"
unless the evidence directly supports the stronger claim.

Limitations documented:
  - Cannot confirm causal relationships from run ordering alone.
  - Does not access Git commit history automatically.
  - Flaky/inconsistent outcomes are flagged when detectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from failscope.models import ParseResult


@dataclass
class SignatureDiff:
    """One entry in the comparison result."""
    signature: str
    status: str   # "new", "disappeared", "persistent"
    baseline_count: int = 0
    candidate_count: int = 0
    baseline_tests: list[str] = field(default_factory=list)
    candidate_tests: list[str] = field(default_factory=list)
    baseline_messages: list[str] = field(default_factory=list)
    candidate_messages: list[str] = field(default_factory=list)


@dataclass
class TestStatusChange:
    """A test that changed pass/fail status between runs."""
    __test__ = False
    test_name: str
    change: str   # "pass_to_fail", "fail_to_pass"
    baseline_message: Optional[str] = None
    candidate_message: Optional[str] = None


@dataclass
class ComparisonResult:
    """Full comparison between baseline and candidate runs."""
    baseline_run_id: Optional[str]
    candidate_run_id: Optional[str]
    baseline_source: Optional[str]
    candidate_source: Optional[str]
    new_failures: list[SignatureDiff] = field(default_factory=list)
    disappeared_failures: list[SignatureDiff] = field(default_factory=list)
    persistent_failures: list[SignatureDiff] = field(default_factory=list)
    test_changes: list[TestStatusChange] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"New: {len(self.new_failures)} | "
            f"Disappeared: {len(self.disappeared_failures)} | "
            f"Persistent: {len(self.persistent_failures)} | "
            f"Test changes: {len(self.test_changes)}"
        )


def _get_signature(record) -> str:
    """Use normalised_signature if available, else first_error_message, else fallback."""
    if record.normalized_signature:
        return record.normalized_signature
    if record.first_error_message:
        return record.first_error_message
    return f"__NO_SIG_{record.error_class or 'unknown'}__"


def compare_runs(
    baseline: ParseResult,
    candidate: ParseResult,
) -> ComparisonResult:
    """
    Compare two parsed regression runs.

    Produces lists of new, disappeared, and persistent failure signatures,
    and test status changes.

    Does NOT infer causality from run ordering alone.
    """
    result = ComparisonResult(
        baseline_run_id=baseline.metadata.run_id,
        candidate_run_id=candidate.metadata.run_id,
        baseline_source=baseline.metadata.source_path,
        candidate_source=candidate.metadata.source_path,
    )

    # Warn if run IDs or commit SHAs suggest uncertain ordering
    if (
        baseline.metadata.commit_sha is None
        and candidate.metadata.commit_sha is None
    ):
        result.warnings.append(
            "Neither run has a commit SHA. Run ordering cannot be verified from metadata alone."
        )
        result.notes.append(
            "Newly observed failures are not confirmed regressions. "
            "Possible confounders: changed seeds, test-set changes, flaky tests."
        )

    # Group by signature
    def group_by_sig(parse_result: ParseResult) -> dict[str, list]:
        groups: dict[str, list] = {}
        for rec in parse_result.failures:
            sig = _get_signature(rec)
            groups.setdefault(sig, []).append(rec)
        return groups

    baseline_sigs = group_by_sig(baseline)
    candidate_sigs = group_by_sig(candidate)

    all_sigs = set(baseline_sigs) | set(candidate_sigs)

    for sig in sorted(all_sigs):
        in_baseline = sig in baseline_sigs
        in_candidate = sig in candidate_sigs

        b_recs = baseline_sigs.get(sig, [])
        c_recs = candidate_sigs.get(sig, [])

        diff = SignatureDiff(
            signature=sig,
            status="persistent" if (in_baseline and in_candidate) else
                   "new" if in_candidate else "disappeared",
            baseline_count=len(b_recs),
            candidate_count=len(c_recs),
            baseline_tests=[r.test_name for r in b_recs if r.test_name],
            candidate_tests=[r.test_name for r in c_recs if r.test_name],
            baseline_messages=[r.first_error_message for r in b_recs if r.first_error_message],
            candidate_messages=[r.first_error_message for r in c_recs if r.first_error_message],
        )

        if diff.status == "new":
            result.new_failures.append(diff)
        elif diff.status == "disappeared":
            result.disappeared_failures.append(diff)
        else:
            result.persistent_failures.append(diff)

    # Test status changes
    baseline_tests = {r.test_name: r for r in baseline.failures if r.test_name}
    candidate_tests = {r.test_name: r for r in candidate.failures if r.test_name}

    for test_name, b_rec in baseline_tests.items():
        if test_name not in candidate_tests:
            result.test_changes.append(TestStatusChange(
                test_name=test_name,
                change="fail_to_pass",
                baseline_message=b_rec.first_error_message,
                candidate_message=None,
            ))

    for test_name, c_rec in candidate_tests.items():
        if test_name not in baseline_tests:
            result.test_changes.append(TestStatusChange(
                test_name=test_name,
                change="pass_to_fail",
                baseline_message=None,
                candidate_message=c_rec.first_error_message,
            ))

    return result
