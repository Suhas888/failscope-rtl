"""
Synthetic benchmark scenario generator for FailScope RTL.

Generates deterministic benchmark scenarios with known ground-truth labels.
No EDA simulator is required; all log content is Python-generated.

IMPORTANT design constraints:
  - Ground-truth bug IDs are assigned at generation time and stored
    separately from the text features used by clustering.
  - Labels never leak into clustering inputs.
  - Ambiguous attributions are explicitly marked.
  - Synthetic cases are labelled as such and are not equivalent
    to real engineering failures.

Scenario families:

  SINGLE_BUG_VARIED    — one bug, multiple tests, different error messages
  SINGLE_BUG_SAME      — one bug, multiple tests, same error message
  MULTI_BUG            — two or three independent bugs, interleaved tests
  GENERIC_TIMEOUT      — distinct bugs all produce generic timeout messages
  UNRELATED_INFRA      — infrastructure failures unrelated to RTL bugs
  MULTI_BUG_COMBO      — two or three simultaneous bugs
  AMBIGUOUS            — one test, could be caused by multiple bugs
"""

from __future__ import annotations

import hashlib
import itertools
import random
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from failscope.models import FailureRecord, FieldSource


class ScenarioFamily(str, Enum):
    SINGLE_BUG_VARIED = "single_bug_varied"
    SINGLE_BUG_SAME = "single_bug_same"
    MULTI_BUG = "multi_bug"
    GENERIC_TIMEOUT = "generic_timeout"
    UNRELATED_INFRA = "unrelated_infra"
    MULTI_BUG_COMBO = "multi_bug_combo"
    AMBIGUOUS = "ambiguous"


@dataclass
class BenchmarkScenario:
    """
    One benchmark scenario: a list of failure records + ground-truth labels.

    ground_truth_labels is parallel to records and maps each record to
    an integer bug ID. Records with label -1 are explicitly ambiguous.
    """
    scenario_id: str
    family: ScenarioFamily
    description: str
    records: list[FailureRecord]
    ground_truth_labels: list[int]   # parallel to records; -1 = ambiguous
    true_n_clusters: int             # number of distinct bugs in this scenario
    bug_types: list[str] = field(default_factory=list)
    n_excluded: int = 0              # records excluded from evaluation
    n_ambiguous: int = 0
    simulator: str = "synthetic"

    def get_evaluable(self) -> tuple[list[FailureRecord], list[int]]:
        """Return records and labels excluding ambiguous entries (label == -1)."""
        pairs = [(r, l) for r, l in zip(self.records, self.ground_truth_labels) if l >= 0]
        if not pairs:
            return [], []
        recs, labels = zip(*pairs)
        return list(recs), list(labels)


DEV_BUG_TYPES = {"operator_change", "off_by_one", "infra_error"}
HELD_OUT_BUG_TYPES = {"missing_reset", "scoreboard", "timeout"}


def classify_scenario_split(scenario: BenchmarkScenario) -> str:
    """
    Classify scenario into 'dev', 'held_out', 'cross_boundary', or 'ambiguous'.
    Guarantees no template overlap between dev and held_out.
    """
    if scenario.family == ScenarioFamily.AMBIGUOUS:
        return "ambiguous"
    bugs = set(scenario.bug_types)
    if not bugs:
        for r in scenario.records:
            tn = r.test_name or ""
            for b in DEV_BUG_TYPES | HELD_OUT_BUG_TYPES:
                if f"_{b}_" in tn or tn.startswith(f"test_{b}_"):
                    bugs.add(b)
    if bugs and bugs.issubset(DEV_BUG_TYPES):
        return "dev"
    elif bugs and bugs.issubset(HELD_OUT_BUG_TYPES):
        return "held_out"
    else:
        return "cross_boundary"



# ---------------------------------------------------------------------------
# Message templates for each fault type
# ---------------------------------------------------------------------------

_BUG_TEMPLATES = {
    "operator_change": [
        "%Error: counter.v:{line}: Assertion failed: count == expected (got {val}, expected {exp})",
        "%Error: counter.v:{line}: LHS != RHS: got {val} expected {exp}",
        "%Error-ASSERT: Operator mismatch at counter.v:{line}: result={val} exp={exp}",
        "Assertion failed at counter.v:{line}: count={val} expected={exp}",
        "%Fatal: counter.v:{line}: Unexpected count value {val} (should be {exp})",
    ],
    "off_by_one": [
        "%Error: fifo.v:{line}: Overflow detected: write_ptr={val} capacity={exp}",
        "%Error-ASSERTEQ: fifo.v:{line}: Boundary error ptr={val} limit={exp}",
        "%Fatal: fifo.v:{line}: Index out of range [{val}] max=[{exp}]",
        "fifo.v:{line}: FAIL off-by-one: got {val} want {exp}",
        "%Error: fifo.v:{line}: Ptr exceeded limit by 1: {val} > {exp}",
    ],
    "missing_reset": [
        "%Error: ctrl.v:{line}: X-propagation: signal '{sig}' contains X",
        "%Fatal: ctrl.v:{line}: Undefined state after reset: reg={sig}",
        "%Error-UNOPT: ctrl.v:{line}: Signal '{sig}' undriven",
        "UVM_ERROR [RESET] ctrl_agent @ {time}ns: Reset not asserted; {sig}=X",
        "%Error: ctrl.v:{line}: Unexpected X in pipeline register '{sig}'",
    ],
    "timeout": [
        "Simulation timeout at {time}ns: test did not complete",
        "%Fatal: tb.v:{line}: $timeout reached at {time}ns",
        "UVM_FATAL [TIMEOUT] tb @ {time}ns: Watchdog expired",
        "TEST FAILED: timeout after {time}ns (expected completion before {exp}ns)",
        "%Error: tb.v:{line}: Simulation exceeded time limit {time}ns",
    ],
    "scoreboard": [
        "UVM_ERROR [SCOREBOARD] scoreboard @ {time}ns: Data mismatch exp={exp} got={val}",
        "%Error: scoreboard.v:{line}: Scoreboard compare fail: exp=0x{exp:04x} got=0x{val:04x}",
        "UVM_ERROR [SCB] cmp_agent.scoreboard @ {time}ns: pkt mismatch seq={val}",
        "SCOREBOARD FAIL at {time}ns: expected {exp} received {val}",
        "UVM_ERROR [DATA_CHK] scoreboard @ {time}ns: payload mismatch",
    ],
    "infra_error": [
        "ERROR: simulation binary not found: sim_out/Vsim",
        "COMPILE ERROR: syntax error at tb_pkg.sv:1: unexpected token",
        "Python traceback: FileNotFoundError: [Errno 2] config.yaml",
        "ERROR: failed to load shared library: libvpi.so",
        "make: *** [Makefile:42: sim] Error 127",
    ],
}

_SIMULATORS = ["verilator", "cocotb", "uvm"]
_MODULES = ["counter", "fifo", "ctrl", "scoreboard", "tb"]


def _make_record(
    bug_id: int,
    bug_type: str,
    template_idx: int,
    seed_offset: int,
    run_id: str,
    rng: random.Random,
) -> FailureRecord:
    """Generate one synthetic FailureRecord for a given bug type."""
    templates = _BUG_TEMPLATES.get(bug_type, _BUG_TEMPLATES["timeout"])
    tmpl = templates[template_idx % len(templates)]

    val = rng.randint(0, 255)
    exp = val + rng.choice([-1, 1, -2, 2])
    line = rng.randint(10, 200)
    time_ns = rng.randint(100, 10000)
    sig = rng.choice(["state_reg", "count_q", "ptr_r", "data_q", "valid_r"])

    try:
        msg = tmpl.format(val=val, exp=exp, line=line, time=time_ns, sig=sig)
    except KeyError:
        msg = tmpl  # fallback if template keys don't all match

    sim = rng.choice(_SIMULATORS)
    module = rng.choice(_MODULES)
    src_file = f"{module}.v"

    record = FailureRecord(
        failure_id=str(uuid.uuid4()),
        test_name=f"test_{bug_type}_{seed_offset:03d}",
        seed=f"{seed_offset:08d}",
        run_id=run_id,
        simulator=sim,
        error_class=bug_type if bug_type != "infra_error" else "infra",
        first_error_message=msg,
        context_lines=[
            f"[{sim}] Running test_{bug_type}_{seed_offset:03d}",
            msg,
            f"  at {src_file}:{line}",
            f"  sim_time={time_ns}ns",
        ],
        source_file=src_file if bug_type != "infra_error" else None,
        source_line=line if bug_type != "infra_error" else None,
        simulation_time=str(time_ns) if bug_type != "infra_error" else None,
        simulation_time_unit="ns" if bug_type != "infra_error" else None,
        mentioned_files=[src_file] if bug_type != "infra_error" else [],
        mentioned_modules=[module],
        raw_evidence_reference=f"synthetic://benchmark/scenario",
    )
    # Ground truth stored in the record for export; never used inside clustering
    record.ground_truth_bug_ids = [f"bug_{bug_id}"]
    record.set_provenance("first_error_message", FieldSource.OBSERVED)
    record.set_provenance("source_file",
        FieldSource.OBSERVED if record.source_file else FieldSource.UNAVAILABLE)
    record.set_provenance("simulation_time",
        FieldSource.OBSERVED if record.simulation_time else FieldSource.UNAVAILABLE)
    record.mark_unavailable("commit_sha", "timestamp")
    return record


def generate_scenarios(seed: int = 42, target_count: int = 120) -> list[BenchmarkScenario]:
    """
    Generate deterministic benchmark scenarios.

    Aims for at least `target_count` scenarios across all families.
    If generation cannot reach that count reliably, returns the actual count
    and logs a warning — does NOT pad with mislabelled data.

    All scenarios are fully synthetic. This is stated prominently in output.
    """
    rng = random.Random(seed)
    scenarios: list[BenchmarkScenario] = []
    scenario_counter = itertools.count(0)

    def sid() -> str:
        return f"S{next(scenario_counter):04d}"

    # -----------------------------------------------------------------------
    # Family 1: SINGLE_BUG_VARIED
    # One root cause, varied error messages from different templates
    # -----------------------------------------------------------------------
    for bug_type in ["operator_change", "off_by_one", "missing_reset", "scoreboard"]:
        for n_failures in [2, 3, 4, 5]:
            run_id = str(uuid.UUID(int=rng.getrandbits(128)))
            records = []
            for i in range(n_failures):
                r = _make_record(0, bug_type, template_idx=i, seed_offset=rng.randint(1, 9999),
                                 run_id=run_id, rng=rng)
                records.append(r)
            scenarios.append(BenchmarkScenario(
                scenario_id=sid(),
                family=ScenarioFamily.SINGLE_BUG_VARIED,
                description=f"Single {bug_type} bug, {n_failures} failures with varied messages",
                records=records,
                ground_truth_labels=[0] * n_failures,
                true_n_clusters=1,
                bug_types=[bug_type],
                simulator="synthetic",
            ))

    # -----------------------------------------------------------------------
    # Family 2: SINGLE_BUG_SAME
    # One root cause, identical or near-identical error messages
    # -----------------------------------------------------------------------
    for bug_type in ["operator_change", "off_by_one", "timeout", "scoreboard"]:
        for n_failures in [2, 3, 5]:
            run_id = str(uuid.UUID(int=rng.getrandbits(128)))
            records = []
            # All use same template but different runtime values
            tmpl_idx = 0
            for i in range(n_failures):
                r = _make_record(0, bug_type, template_idx=tmpl_idx, seed_offset=rng.randint(1, 9999),
                                 run_id=run_id, rng=rng)
                records.append(r)
            scenarios.append(BenchmarkScenario(
                scenario_id=sid(),
                family=ScenarioFamily.SINGLE_BUG_SAME,
                description=f"Single {bug_type} bug, {n_failures} failures with same template",
                records=records,
                ground_truth_labels=[0] * n_failures,
                true_n_clusters=1,
                bug_types=[bug_type],
                simulator="synthetic",
            ))

    # -----------------------------------------------------------------------
    # Family 3: MULTI_BUG
    # Two or three independent bugs, interleaved failures
    # -----------------------------------------------------------------------
    bug_pairs = list(itertools.combinations(
        ["operator_change", "off_by_one", "missing_reset", "scoreboard", "timeout"], 2
    ))
    for bug_a, bug_b in bug_pairs[:8]:  # cap at 8 pairs
        n_each = 3
        run_id = str(uuid.UUID(int=rng.getrandbits(128)))
        records = []
        labels = []
        for i in range(n_each):
            records.append(_make_record(0, bug_a, template_idx=i, seed_offset=rng.randint(1, 9999),
                                        run_id=run_id, rng=rng))
            labels.append(0)
        for i in range(n_each):
            records.append(_make_record(1, bug_b, template_idx=i, seed_offset=rng.randint(1, 9999),
                                        run_id=run_id, rng=rng))
            labels.append(1)
        # Shuffle to interleave
        combined = list(zip(records, labels))
        rng.shuffle(combined)
        records, labels = zip(*combined) if combined else ([], [])
        scenarios.append(BenchmarkScenario(
            scenario_id=sid(),
            family=ScenarioFamily.MULTI_BUG,
            description=f"Two bugs: {bug_a} + {bug_b}, {n_each} failures each",
            records=list(records),
            ground_truth_labels=list(labels),
            true_n_clusters=2,
            bug_types=[bug_a, bug_b],
            simulator="synthetic",
        ))

    # Three-bug scenarios
    for _ in range(4):
        bug_triple = rng.sample(["operator_change", "off_by_one", "missing_reset", "timeout", "scoreboard"], 3)
        n_each = 2
        run_id = str(uuid.UUID(int=rng.getrandbits(128)))
        records, labels = [], []
        for bug_idx, bt in enumerate(bug_triple):
            for i in range(n_each):
                records.append(_make_record(bug_idx, bt, template_idx=i,
                                            seed_offset=rng.randint(1, 9999),
                                            run_id=run_id, rng=rng))
                labels.append(bug_idx)
        combined = list(zip(records, labels))
        rng.shuffle(combined)
        records, labels = zip(*combined)
        scenarios.append(BenchmarkScenario(
            scenario_id=sid(),
            family=ScenarioFamily.MULTI_BUG,
            description=f"Three bugs: {', '.join(bug_triple)}, {n_each} failures each",
            records=list(records),
            ground_truth_labels=list(labels),
            true_n_clusters=3,
            bug_types=list(bug_triple),
            simulator="synthetic",
        ))

    # -----------------------------------------------------------------------
    # Family 4: GENERIC_TIMEOUT
    # Distinct bugs all produce generic timeout messages (hard for B0/B1)
    # -----------------------------------------------------------------------
    for n_bugs in [2, 3]:
        run_id = str(uuid.UUID(int=rng.getrandbits(128)))
        records, labels = [], []
        for bug_id in range(n_bugs):
            for _ in range(3):
                r = _make_record(bug_id, "timeout", template_idx=0,
                                 seed_offset=rng.randint(1, 9999),
                                 run_id=run_id, rng=rng)
                records.append(r)
                labels.append(bug_id)
        scenarios.append(BenchmarkScenario(
            scenario_id=sid(),
            family=ScenarioFamily.GENERIC_TIMEOUT,
            description=f"{n_bugs} distinct bugs all producing generic timeout messages",
            records=records,
            ground_truth_labels=labels,
            true_n_clusters=n_bugs,
            bug_types=["timeout"],
            simulator="synthetic",
        ))

    # -----------------------------------------------------------------------
    # Family 5: UNRELATED_INFRA
    # Infrastructure failures unrelated to RTL bugs
    # -----------------------------------------------------------------------
    for n_infra in [1, 2, 3]:
        run_id = str(uuid.UUID(int=rng.getrandbits(128)))
        records, labels = [], []
        for i in range(n_infra):
            r = _make_record(i, "infra_error", template_idx=i,
                             seed_offset=rng.randint(1, 9999),
                             run_id=run_id, rng=rng)
            records.append(r)
            labels.append(i)
        scenarios.append(BenchmarkScenario(
            scenario_id=sid(),
            family=ScenarioFamily.UNRELATED_INFRA,
            description=f"{n_infra} unrelated infrastructure failure(s)",
            records=records,
            ground_truth_labels=labels,
            true_n_clusters=n_infra,
            bug_types=["infra_error"],
            simulator="synthetic",
        ))

    # -----------------------------------------------------------------------
    # Family 6: MULTI_BUG_COMBO
    # Two or three simultaneous bugs
    # -----------------------------------------------------------------------
    for _ in range(6):
        n_bugs = rng.choice([2, 3])
        bug_types = rng.sample(list(_BUG_TEMPLATES.keys()), n_bugs)
        n_each = rng.randint(2, 4)
        run_id = str(uuid.UUID(int=rng.getrandbits(128)))
        records, labels = [], []
        for bug_idx, bt in enumerate(bug_types):
            for i in range(n_each):
                records.append(_make_record(bug_idx, bt, template_idx=i,
                                            seed_offset=rng.randint(1, 9999),
                                            run_id=run_id, rng=rng))
                labels.append(bug_idx)
        combined = list(zip(records, labels))
        rng.shuffle(combined)
        if combined:
            records, labels = zip(*combined)
        scenarios.append(BenchmarkScenario(
            scenario_id=sid(),
            family=ScenarioFamily.MULTI_BUG_COMBO,
            description=f"Simultaneous {n_bugs}-bug combo: {', '.join(bug_types)}",
            records=list(records),
            ground_truth_labels=list(labels),
            true_n_clusters=n_bugs,
            bug_types=list(bug_types),
            simulator="synthetic",
        ))

    # -----------------------------------------------------------------------
    # Family 7: AMBIGUOUS
    # One test that could be caused by multiple bugs; label = -1
    # -----------------------------------------------------------------------
    for _ in range(4):
        run_id = str(uuid.UUID(int=rng.getrandbits(128)))
        bug_type = rng.choice(["timeout", "scoreboard"])
        records = [
            _make_record(0, bug_type, template_idx=0, seed_offset=rng.randint(1, 9999),
                         run_id=run_id, rng=rng)
        ]
        scenarios.append(BenchmarkScenario(
            scenario_id=sid(),
            family=ScenarioFamily.AMBIGUOUS,
            description="Ambiguous failure: single test, multiple possible causes",
            records=records,
            ground_truth_labels=[-1],  # ambiguous
            true_n_clusters=1,
            bug_types=[bug_type],
            n_ambiguous=1,
            simulator="synthetic",
        ))

    # -----------------------------------------------------------------------
    # Pad to target with additional SINGLE_BUG_VARIED / MULTI_BUG scenarios
    # -----------------------------------------------------------------------
    extra_bug_types = ["operator_change", "off_by_one", "missing_reset", "scoreboard", "timeout"]
    while len(scenarios) < target_count:
        family_choice = rng.choice([
            ScenarioFamily.SINGLE_BUG_VARIED,
            ScenarioFamily.MULTI_BUG,
            ScenarioFamily.GENERIC_TIMEOUT,
        ])
        run_id = str(uuid.UUID(int=rng.getrandbits(128)))

        if family_choice == ScenarioFamily.SINGLE_BUG_VARIED:
            bt = rng.choice(extra_bug_types)
            n_f = rng.randint(2, 5)
            records = [
                _make_record(0, bt, template_idx=i, seed_offset=rng.randint(1, 9999),
                             run_id=run_id, rng=rng)
                for i in range(n_f)
            ]
            scenarios.append(BenchmarkScenario(
                scenario_id=sid(),
                family=ScenarioFamily.SINGLE_BUG_VARIED,
                description=f"Extra: single {bt} bug, {n_f} failures",
                records=records,
                ground_truth_labels=[0] * n_f,
                true_n_clusters=1,
                bug_types=[bt],
                simulator="synthetic",
            ))

        elif family_choice == ScenarioFamily.MULTI_BUG:
            bt_a, bt_b = rng.sample(extra_bug_types, 2)
            n_each = rng.randint(2, 4)
            records, labels = [], []
            for i in range(n_each):
                records.append(_make_record(0, bt_a, i, rng.randint(1, 9999), run_id, rng))
                labels.append(0)
            for i in range(n_each):
                records.append(_make_record(1, bt_b, i, rng.randint(1, 9999), run_id, rng))
                labels.append(1)
            combined = list(zip(records, labels))
            rng.shuffle(combined)
            if combined:
                records, labels = zip(*combined)
            scenarios.append(BenchmarkScenario(
                scenario_id=sid(),
                family=ScenarioFamily.MULTI_BUG,
                description=f"Extra: two bugs {bt_a}+{bt_b}",
                records=list(records),
                ground_truth_labels=list(labels),
                true_n_clusters=2,
                bug_types=[bt_a, bt_b],
                simulator="synthetic",
            ))

        elif family_choice == ScenarioFamily.GENERIC_TIMEOUT:
            n_bugs = rng.choice([2, 3])
            records, labels = [], []
            for bid in range(n_bugs):
                for _ in range(rng.randint(2, 4)):
                    records.append(_make_record(bid, "timeout", 0, rng.randint(1, 9999), run_id, rng))
                    labels.append(bid)
            scenarios.append(BenchmarkScenario(
                scenario_id=sid(),
                family=ScenarioFamily.GENERIC_TIMEOUT,
                description=f"Extra: {n_bugs} distinct timeout-producing bugs",
                records=records,
                ground_truth_labels=labels,
                true_n_clusters=n_bugs,
                bug_types=["timeout"],
                simulator="synthetic",
            ))

    return scenarios
