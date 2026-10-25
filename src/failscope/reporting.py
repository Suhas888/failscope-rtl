"""
HTML report generator for FailScope RTL.

Produces a self-contained, offline-usable HTML report.

Security requirements (all enforced):
  - All log content is HTML-escaped before insertion.
  - No external runtime dependencies (no CDN, no JS fetch).
  - No executable HTML/JS from log content.
  - Local file links only when path is safe and resolvable.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from failscope.clustering import ClusterResult
from failscope.comparison import ComparisonResult
from failscope.models import ParseResult


# ---------------------------------------------------------------------------
# CSS embedded in the report (no external dependency)
# ---------------------------------------------------------------------------
_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: #0f1117;
  color: #e2e8f0;
  line-height: 1.6;
  font-size: 14px;
}
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; }

/* Header */
.header {
  background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
  border-bottom: 1px solid #334155;
  padding: 24px 32px;
}
.header h1 { font-size: 22px; font-weight: 700; color: #f1f5f9; }
.header .subtitle { color: #94a3b8; font-size: 13px; margin-top: 4px; }
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  margin-left: 8px;
}
.badge-warn { background: #451a03; color: #fed7aa; }
.badge-info { background: #1e3a5f; color: #93c5fd; }
.badge-ok   { background: #14532d; color: #86efac; }

/* Layout */
.container { max-width: 1200px; margin: 0 auto; padding: 24px 32px; }
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.meta-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 14px 16px;
}
.meta-card .label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .5px; }
.meta-card .value { font-size: 18px; font-weight: 700; color: #f1f5f9; margin-top: 4px; }

/* Sections */
.section { margin-bottom: 32px; }
.section-title {
  font-size: 15px;
  font-weight: 700;
  color: #cbd5e1;
  border-bottom: 1px solid #334155;
  padding-bottom: 8px;
  margin-bottom: 16px;
}

/* Cluster cards */
.cluster-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-left: 4px solid #3b82f6;
  border-radius: 8px;
  margin-bottom: 14px;
  overflow: hidden;
}
.cluster-card.severity-fatal { border-left-color: #ef4444; }
.cluster-card.severity-error { border-left-color: #f59e0b; }
.cluster-card.severity-info  { border-left-color: #22c55e; }

.cluster-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}
.cluster-header:hover { background: #243044; }
.cluster-id { font-size: 11px; font-weight: 700; color: #64748b; min-width: 60px; }
.cluster-count {
  background: #374151;
  color: #d1d5db;
  border-radius: 12px;
  padding: 1px 8px;
  font-size: 11px;
  font-weight: 600;
}
.cluster-sig {
  flex: 1;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 12px;
  color: #93c5fd;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cluster-body { padding: 0 16px 14px; border-top: 1px solid #334155; }
.cluster-body.hidden { display: none; }

/* Evidence blocks */
.evidence {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 10px 14px;
  margin-top: 10px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 11px;
  color: #94a3b8;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.evidence .err-line { color: #fca5a5; }
.evidence .warn-line { color: #fde68a; }

/* Warnings */
.warn-box {
  background: #451a03;
  border: 1px solid #7c2d12;
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 14px;
  font-size: 12px;
  color: #fed7aa;
}
.warn-box ul { padding-left: 18px; }

/* Comparison */
.diff-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.diff-table th {
  background: #1e293b;
  color: #94a3b8;
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid #334155;
  font-weight: 600;
}
.diff-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #1e293b;
  vertical-align: top;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.diff-table tr.new td { color: #86efac; }
.diff-table tr.disappeared td { color: #fca5a5; }
.diff-table tr.persistent td { color: #94a3b8; }

/* Footer */
.footer {
  margin-top: 48px;
  padding: 20px 32px;
  border-top: 1px solid #1e293b;
  font-size: 11px;
  color: #475569;
}

/* Toggle chevron */
.toggle-icon { font-size: 10px; color: #4b5563; }

/* Disclaimer */
.disclaimer {
  background: #1c1917;
  border: 1px solid #44403c;
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 20px;
  font-size: 12px;
  color: #a8a29e;
}
"""

_JS = """
function toggleCluster(id) {
  var body = document.getElementById('body-' + id);
  if (body) {
    body.classList.toggle('hidden');
  }
}
"""


def _e(text: Optional[str]) -> str:
    """HTML-escape a string. Returns empty string for None."""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def _severity_class(error_class: Optional[str]) -> str:
    ec = (error_class or "").lower()
    if "fatal" in ec:
        return "severity-fatal"
    if "error" in ec or "assertion" in ec:
        return "severity-error"
    return "severity-info"


def _render_meta_card(label: str, value: str) -> str:
    return (
        f'<div class="meta-card">'
        f'<div class="label">{_e(label)}</div>'
        f'<div class="value">{_e(value)}</div>'
        f'</div>'
    )


def _render_warnings(warnings: list[str]) -> str:
    if not warnings:
        return ""
    items = "".join(f"<li>{_e(w)}</li>" for w in warnings)
    return f'<div class="warn-box"><strong>⚠ Parser warnings:</strong><ul>{items}</ul></div>'


def _render_cluster_card(
    cluster_id: int,
    records: list,
    method: str,
) -> str:
    rep = records[0]
    sig = rep.normalized_signature or rep.first_error_message or "(no signature)"
    sev_class = _severity_class(rep.error_class)
    card_id = f"{method}-{cluster_id}"

    # Header
    tests = list(dict.fromkeys(r.test_name for r in records if r.test_name))
    test_str = ", ".join(tests[:5]) + ("…" if len(tests) > 5 else "")

    header = (
        f'<div class="cluster-header" onclick="toggleCluster(\'{_e(card_id)}\')" '
        f'id="header-{_e(card_id)}">'
        f'<span class="cluster-id">Cluster {cluster_id}</span>'
        f'<span class="cluster-count">{len(records)} failure{"s" if len(records)!=1 else ""}</span>'
        f'<span class="cluster-sig">{_e(sig)}</span>'
        f'<span class="toggle-icon">▼</span>'
        f'</div>'
    )

    # Body
    body_parts = []

    # Error class / representative message
    if rep.error_class:
        body_parts.append(f'<p style="margin-top:10px;font-size:12px;color:#64748b;">Error class: <strong style="color:#cbd5e1">{_e(rep.error_class)}</strong></p>')

    if test_str:
        body_parts.append(f'<p style="font-size:12px;color:#64748b;margin-top:4px;">Tests: <span style="color:#94a3b8">{_e(test_str)}</span></p>')

    # Source location
    if rep.source_file:
        loc = f"{rep.source_file}:{rep.source_line}" if rep.source_line else rep.source_file
        body_parts.append(f'<p style="font-size:12px;color:#64748b;margin-top:4px;">Source: <code style="color:#67e8f9">{_e(loc)}</code></p>')

    # Evidence box (escaped)
    evidence_lines = []
    for rec in records[:3]:
        if rec.context_lines:
            evidence_lines.append(f"# {rec.test_name or rec.failure_id}")
            for ln in rec.context_lines[:6]:
                cls = "err-line" if ("%error" in ln.lower() or "%fatal" in ln.lower() or "uvm_error" in ln.lower()) else ""
                evidence_lines.append(f'<span class="{cls}">{_e(ln)}</span>')
            evidence_lines.append("")

    if evidence_lines:
        evidence_html = "\n".join(evidence_lines)
        body_parts.append(f'<div class="evidence">{evidence_html}</div>')

    body_parts.append(
        '<p style="font-size:11px;color:#475569;margin-top:8px;font-style:italic;">'
        '⚠ A cluster is not proof of a unique root cause. Inspect supporting evidence before acting.</p>'
    )

    body = (
        f'<div class="cluster-body hidden" id="body-{_e(card_id)}">'
        + "".join(body_parts)
        + "</div>"
    )

    return f'<div class="cluster-card {sev_class}">{header}{body}</div>'


def _group_by_cluster(records: list, labels: list[int]) -> dict[int, list]:
    groups: dict[int, list] = {}
    for rec, label in zip(records, labels):
        groups.setdefault(label, []).append(rec)
    return groups


def generate_report(
    parse_result: ParseResult,
    cluster_result: Optional[ClusterResult] = None,
    comparison: Optional[ComparisonResult] = None,
    output_path: Optional[str | Path] = None,
    title: str = "FailScope RTL Report",
) -> str:
    """
    Generate a self-contained HTML report.

    All user-supplied content is HTML-escaped.
    Returns the HTML string; optionally writes to output_path.
    """
    meta = parse_result.metadata
    failures = parse_result.failures
    method = cluster_result.method if cluster_result else "none"

    # --- Metadata cards ---
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cards = [
        _render_meta_card("Generated", now_str),
        _render_meta_card("Run ID", (meta.run_id or "unknown")[:16] + "…"),
        _render_meta_card("Simulator", meta.simulator or "unknown"),
        _render_meta_card("Total Tests", str(meta.total_tests or "unknown")),
        _render_meta_card("Failed Tests", str(meta.failed_tests or len(failures))),
        _render_meta_card("Failure Records", str(len(failures))),
        _render_meta_card("Clustering", method),
    ]
    if cluster_result:
        cards.append(_render_meta_card("Clusters", str(cluster_result.n_clusters)))

    meta_html = '<div class="meta-grid">' + "".join(cards) + "</div>"

    # --- Disclaimer ---
    disclaimer = (
        '<div class="disclaimer">'
        '<strong>FailScope RTL</strong> groups failures by likely shared signature. '
        'Cluster membership is not proof of a unique root cause. '
        'All processing is local. No data is transmitted. '
        'See supporting evidence for each cluster before acting on results.'
        '</div>'
    )

    # --- Warnings ---
    all_warnings = list(meta.parse_warnings)
    if cluster_result:
        all_warnings.extend(cluster_result.warnings)
    warnings_html = _render_warnings(all_warnings)

    # --- Clusters ---
    clusters_html = ""
    if cluster_result and failures:
        groups = _group_by_cluster(failures, cluster_result.labels)
        sorted_groups = sorted(groups.items(), key=lambda kv: -len(kv[1]))
        cluster_cards = [
            _render_cluster_card(cid, recs, method)
            for cid, recs in sorted_groups
        ]
        clusters_html = (
            '<div class="section">'
            f'<div class="section-title">Failure Clusters ({len(groups)} groups, {method} method)</div>'
            + "".join(cluster_cards)
            + "</div>"
        )
    elif failures:
        # No clustering — just list failures
        items = []
        for i, rec in enumerate(failures):
            sig = rec.normalized_signature or rec.first_error_message or "(no message)"
            items.append(
                f'<div class="cluster-card {_severity_class(rec.error_class)}">'
                f'<div class="cluster-header">'
                f'<span class="cluster-id">#{i+1}</span>'
                f'<span class="cluster-sig">{_e(sig)}</span>'
                f'</div></div>'
            )
        clusters_html = (
            '<div class="section">'
            f'<div class="section-title">Failures ({len(failures)} total)</div>'
            + "".join(items) + "</div>"
        )

    # --- Comparison ---
    comparison_html = ""
    if comparison:
        rows = []
        for diff in comparison.new_failures:
            rows.append(
                f'<tr class="new"><td>NEW</td>'
                f'<td><code>{_e(diff.signature[:120])}</code></td>'
                f'<td>{diff.candidate_count}</td>'
                f'<td>{_e(", ".join(diff.candidate_tests[:3]))}</td></tr>'
            )
        for diff in comparison.disappeared_failures:
            rows.append(
                f'<tr class="disappeared"><td>GONE</td>'
                f'<td><code>{_e(diff.signature[:120])}</code></td>'
                f'<td>{diff.baseline_count}</td>'
                f'<td>{_e(", ".join(diff.baseline_tests[:3]))}</td></tr>'
            )
        for diff in comparison.persistent_failures:
            rows.append(
                f'<tr class="persistent"><td>PERSIST</td>'
                f'<td><code>{_e(diff.signature[:120])}</code></td>'
                f'<td>{diff.baseline_count}→{diff.candidate_count}</td>'
                f'<td></td></tr>'
            )
        comp_warn = _render_warnings(comparison.warnings + comparison.notes)
        table = (
            '<table class="diff-table">'
            '<thead><tr><th>Status</th><th>Signature</th><th>Count</th><th>Tests</th></tr></thead>'
            '<tbody>' + "".join(rows) + '</tbody>'
            '</table>'
        )
        comparison_html = (
            '<div class="section">'
            '<div class="section-title">Run Comparison</div>'
            + comp_warn + table
            + "</div>"
        )

    # --- Source info ---
    source_str = _e(meta.source_path or "unknown")
    commit_str = _e(meta.commit_sha or "not available")

    # --- Full HTML ---
    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_e(title)}</title>
<meta name="description" content="FailScope RTL simulation regression failure report">
<style>{_CSS}</style>
</head>
<body>
<div class="header">
  <h1>🔬 {_e(title)}</h1>
  <div class="subtitle">
    Source: {source_str} &nbsp;|&nbsp;
    Commit: {commit_str} &nbsp;|&nbsp;
    <em>Local processing only — no data transmitted</em>
  </div>
</div>
<div class="container">
  {disclaimer}
  {meta_html}
  {warnings_html}
  {comparison_html}
  {clusters_html}
  <div class="footer">
    Generated by FailScope RTL v0.1.0 &mdash;
    Synthetic/heuristic grouping only. Not a substitute for manual root-cause analysis.
    All log content is HTML-escaped. No external resources loaded.
  </div>
</div>
<script>{_JS}</script>
</body>
</html>"""

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(body, encoding="utf-8")

    return body
