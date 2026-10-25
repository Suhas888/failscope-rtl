"""
Command-line interface for FailScope RTL.

Commands:
  failscope parse <input>
  failscope analyze <input> --out <report.html>
  failscope compare <baseline> <candidate> --out <report.html>
  failscope benchmark --out <directory>
  failscope evaluate <benchmark-directory>
  failscope doctor
  failscope version

All commands:
  - Support --verbose for diagnostics
  - Return nonzero exit codes on errors
  - Never overwrite an existing report without --force
  - Never execute arbitrary content from logs
  - Use safe argument lists for subprocesses
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from failscope import __version__


def _require_output(out: Optional[str], force: bool) -> Path:
    """Validate output path; refuse to overwrite without --force."""
    if not out:
        print("ERROR: --out is required for this command.", file=sys.stderr)
        sys.exit(2)
    p = Path(out)
    if p.exists() and not force:
        print(
            f"ERROR: Output file already exists: {p}\n"
            "Use --force to overwrite.",
            file=sys.stderr,
        )
        sys.exit(2)
    return p


def cmd_version(args: argparse.Namespace) -> int:
    print(f"FailScope RTL {__version__}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check environment and dependencies."""
    import importlib

    issues: list[str] = []
    ok: list[str] = []

    deps = [
        ("sklearn", "scikit-learn"),
        ("numpy", "numpy"),
    ]
    for mod, pkg in deps:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "?")
            ok.append(f"  [OK] {pkg} {ver}")
        except ImportError:
            issues.append(f"  [FAIL] {pkg} not installed -- run: pip install {pkg}")

    # Simulators (not required)
    import shutil
    simulators = ["verilator", "iverilog", "vcs"]
    for sim in simulators:
        path = shutil.which(sim)
        if path:
            ok.append(f"  [OK] simulator: {sim} ({path})")
        else:
            ok.append(f"  [-] simulator: {sim} not found (not required)")

    print("FailScope RTL -- environment check")
    print("=" * 40)
    for line in ok:
        print(line)
    if issues:
        print("\nIssues:")
        for line in issues:
            print(line)
        return 1
    print("\nAll required dependencies found.")
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    """Parse a log or XML file and print summary."""
    from failscope.ingest import ingest, ingest_directory
    from failscope.signatures import compute_b1_signature

    path = Path(args.input)
    if not path.exists():
        print(f"ERROR: Input not found: {path}", file=sys.stderr)
        return 1

    verbose = getattr(args, "verbose", False)
    fmt = getattr(args, "format", None)

    if path.is_dir():
        results = ingest_directory(path, fmt=fmt)
    else:
        results = [ingest(path, fmt=fmt)]

    total_failures = 0
    for result in results:
        meta = result.metadata
        print(f"\nSource: {meta.source_path}")
        print(f"  Simulator : {meta.simulator or 'unknown'}")
        print(f"  Failures  : {len(result.failures)}")
        if meta.parse_warnings:
            for w in meta.parse_warnings:
                print(f"  WARN: {w}")
        total_failures += len(result.failures)

        for i, rec in enumerate(result.failures):
            sig = compute_b1_signature(rec)
            if verbose:
                print(f"  [{i+1}] {rec.error_class or '?'} | {rec.first_error_message or '?'}")
                print(f"       sig: {sig}")
            else:
                print(f"  [{i+1}] {sig[:100]}")

    print(f"\nTotal failures parsed: {total_failures}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Parse, cluster, and generate an HTML report."""
    from failscope.ingest import ingest, ingest_directory
    from failscope.clustering import ClusteringConfig, run_all_methods
    from failscope.signatures import compute_b1_signature
    from failscope.reporting import generate_report
    from failscope.models import ParseResult

    path = Path(args.input)
    if not path.exists():
        print(f"ERROR: Input not found: {path}", file=sys.stderr)
        return 1

    out_path = _require_output(getattr(args, "out", None), getattr(args, "force", False))
    method = getattr(args, "method", "B1").upper()
    fmt = getattr(args, "format", None)

    if path.is_dir():
        results = ingest_directory(path, fmt=fmt)
        # Merge into a single ParseResult
        from failscope.models import RunMetadata
        import uuid
        merged_meta = RunMetadata(run_id=str(uuid.uuid4()), source_path=str(path))
        all_failures = []
        for r in results:
            merged_meta.parse_warnings.extend(r.metadata.parse_warnings)
            all_failures.extend(r.failures)
        merged_meta.failed_tests = len(all_failures)
        parse_result = ParseResult(metadata=merged_meta, failures=all_failures)
    else:
        parse_result = ingest(path, fmt=fmt)

    # Compute B1 signatures
    for rec in parse_result.failures:
        rec.normalized_signature = compute_b1_signature(rec)

    if not parse_result.failures:
        print("No failures found; generating empty report.")
        generate_report(parse_result, output_path=out_path)
        print(f"Report written: {out_path}")
        return 0

    cfg = ClusteringConfig()
    all_results = run_all_methods(parse_result.failures, cfg)
    cluster_result = all_results.get(method, all_results["B1"])

    print(f"Parsed {len(parse_result.failures)} failure(s), {cluster_result.n_clusters} cluster(s) ({method})")

    generate_report(parse_result, cluster_result=cluster_result, output_path=out_path)
    print(f"Report written: {out_path}")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare two regression runs and generate a report."""
    from failscope.ingest import ingest
    from failscope.comparison import compare_runs
    from failscope.reporting import generate_report
    from failscope.signatures import compute_b1_signature

    baseline_path = Path(args.baseline)
    candidate_path = Path(args.candidate)

    for p in [baseline_path, candidate_path]:
        if not p.exists():
            print(f"ERROR: Input not found: {p}", file=sys.stderr)
            return 1

    out_path = _require_output(getattr(args, "out", None), getattr(args, "force", False))

    baseline = ingest(baseline_path)
    candidate = ingest(candidate_path)

    for rec in baseline.failures + candidate.failures:
        rec.normalized_signature = compute_b1_signature(rec)

    comparison = compare_runs(baseline, candidate)
    print(comparison.summary())

    generate_report(
        candidate,
        comparison=comparison,
        output_path=out_path,
        title="FailScope RTL -- Run Comparison",
    )
    print(f"Report written: {out_path}")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run the synthetic benchmark and save results."""
    from failscope.benchmark.runner import run_benchmark

    out_dir = getattr(args, "out", "benchmark_results")
    seed = getattr(args, "seed", 42)

    print(
        "\nNOTE: This benchmark uses entirely synthetic Python-generated log data.\n"
        "Results describe clustering performance on synthetic scenarios only.\n"
        "They are NOT equivalent to performance on real engineering failures.\n"
    )

    run_benchmark(output_dir=out_dir, seed=seed)
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    """Load and display saved benchmark results."""
    import json

    bdir = Path(args.benchmark_dir)
    summary_path = bdir / "summary.json"

    if not summary_path.exists():
        print(f"ERROR: No summary.json in {bdir}. Run 'failscope benchmark' first.", file=sys.stderr)
        return 1

    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    print(f"\n=== Benchmark Evaluation ===")
    print(f"Scenarios : {summary.get('scenario_count', '?')}")
    print(f"Seed      : {summary.get('benchmark_seed', '?')}")
    print(f"\nNote: {summary.get('note', '')}\n")

    methods = summary.get("methods", {})
    print(f"{'Method':<6} {'ARI':>8} {'ARI-CI 95%':>18} {'V-meas':>8} {'AbsErr':>8} {'ExactAcc':>10}")
    print("-" * 64)
    for m in ["B0", "B1", "B2", "B3"]:
        if m not in methods:
            continue
        d = methods[m]
        ari = f"{d['mean_ari']:.4f}" if d["mean_ari"] is not None else "  N/A"
        ci = d.get("ari_ci_95", [None, None])
        ci_str = f"[{ci[0]:.3f},{ci[1]:.3f}]" if ci[0] is not None else "       N/A"
        vm = f"{d['mean_v_measure']:.4f}" if d["mean_v_measure"] is not None else "  N/A"
        ae = f"{d['mean_abs_cluster_error']:.3f}" if d["mean_abs_cluster_error"] is not None else "  N/A"
        ea = f"{d['exact_count_accuracy']:.4f}" if d["exact_count_accuracy"] is not None else "  N/A"
        print(f"{m:<6} {ari:>8} {ci_str:>18} {vm:>8} {ae:>8} {ea:>10}")

    gate = summary.get("gate", {})
    overall = gate.get("overall", "unknown").upper()
    print(f"\nOverall benchmark gate: {overall}")
    for k, v in gate.items():
        if k in ("overall", "min_improvement_threshold"):
            continue
        if isinstance(v, dict):
            delta_str = f"  delta={v.get('delta', 0):.4f}" if "delta" in v else ""
            print(f"  {k}: {v.get('result','?')}{delta_str}")

    splits = summary.get("splits", {})
    if "held_out" in splits:
        hg = splits["held_out"].get("gate", {})
        print(f"\nHeld-out split gate: {hg.get('overall', 'unknown').upper()}")
        for k, v in hg.items():
            if k in ("overall", "min_improvement_threshold"):
                continue
            if isinstance(v, dict):
                delta_str = f"  delta={v.get('delta', 0):.4f}" if "delta" in v else ""
                ci = v.get("paired_ci_95")
                ci_str = f"  95% CI=[{ci[0]:.4f}, {ci[1]:.4f}]" if ci else ""
                print(f"  {k}: {v.get('result','?')}{delta_str}{ci_str}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="failscope",
        description="FailScope RTL -- local-first RTL simulation regression failure investigator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  failscope parse examples/logs/verilator_example.log
  failscope analyze examples/logs/verilator_example.log --out report.html
  failscope compare baseline.log candidate.log --out compare.html
  failscope benchmark --out benchmark_results/
  failscope evaluate benchmark_results/
  failscope doctor
  failscope version
        """,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose diagnostics")

    sub = parser.add_subparsers(dest="command")

    # version
    sub.add_parser("version", help="Print version and exit")

    # doctor
    sub.add_parser("doctor", help="Check environment and dependencies")

    # parse
    p_parse = sub.add_parser("parse", help="Parse a log or XML file")
    p_parse.add_argument("input", help="Input file or directory")
    p_parse.add_argument("--format", choices=["auto", "junit_xml", "verilator", "uvm"],
                         default="auto", help="Force input format (default: auto)")

    # analyze
    p_analyze = sub.add_parser("analyze", help="Parse, cluster, and generate HTML report")
    p_analyze.add_argument("input", help="Input file or directory")
    p_analyze.add_argument("--out", required=True, help="Output HTML report path")
    p_analyze.add_argument("--method", choices=["B0", "B1", "B2", "B3"], default="B1",
                           help="Clustering method (default: B1)")
    p_analyze.add_argument("--format", choices=["auto", "junit_xml", "verilator", "uvm"],
                           default="auto")
    p_analyze.add_argument("--force", action="store_true", help="Overwrite existing output")

    # compare
    p_compare = sub.add_parser("compare", help="Compare two regression runs")
    p_compare.add_argument("baseline", help="Baseline log/XML")
    p_compare.add_argument("candidate", help="Candidate log/XML")
    p_compare.add_argument("--out", required=True, help="Output HTML report path")
    p_compare.add_argument("--force", action="store_true", help="Overwrite existing output")

    # benchmark
    p_bench = sub.add_parser("benchmark", help="Run synthetic benchmark")
    p_bench.add_argument("--out", default="benchmark_results", help="Output directory")
    p_bench.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Display saved benchmark results")
    p_eval.add_argument("benchmark_dir", help="Directory containing benchmark results")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "version": cmd_version,
        "doctor": cmd_doctor,
        "parse": cmd_parse,
        "analyze": cmd_analyze,
        "compare": cmd_compare,
        "benchmark": cmd_benchmark,
        "evaluate": cmd_evaluate,
    }

    if not args.command:
        parser.print_help()
        return 0

    handler = dispatch.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    try:
        return handler(args) or 0
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
