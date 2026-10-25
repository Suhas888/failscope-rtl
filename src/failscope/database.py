"""
SQLite storage for FailScope RTL.

Stores run metadata and failure records for run comparison and history.
Schema is versioned; migrations are applied at connect time.

Privacy: no secrets, credentials, or environment variables are stored.
Users can delete the database file to remove all local history.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from failscope.models import FailureRecord, RunMetadata

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    simulator   TEXT,
    commit_sha  TEXT,
    timestamp   TEXT,
    total_tests INTEGER,
    failed_tests INTEGER,
    passed_tests INTEGER,
    skipped_tests INTEGER,
    source_path TEXT,
    parse_warnings TEXT,   -- JSON array
    extra       TEXT,      -- JSON object
    imported_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS failures (
    failure_id          TEXT PRIMARY KEY,
    run_id              TEXT REFERENCES runs(run_id),
    test_name           TEXT,
    seed                TEXT,
    commit_sha          TEXT,
    timestamp           TEXT,
    simulator           TEXT,
    error_class         TEXT,
    first_error_message TEXT,
    normalized_signature TEXT,
    context_lines       TEXT,  -- JSON array
    source_file         TEXT,
    source_line         INTEGER,
    simulation_time     TEXT,
    simulation_time_unit TEXT,
    mentioned_files     TEXT,  -- JSON array
    mentioned_modules   TEXT,  -- JSON array
    exit_code           INTEGER,
    parse_warnings      TEXT,  -- JSON array
    raw_evidence_reference TEXT,
    provenance          TEXT   -- JSON object
    -- NOTE: ground_truth_bug_ids intentionally NOT stored here
);
"""


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply schema migrations."""
    cur = conn.execute("SELECT COUNT(*) FROM schema_version")
    if cur.fetchone()[0] == 0:
        conn.execute("INSERT INTO schema_version(version) VALUES (?)", (_SCHEMA_VERSION,))
        conn.commit()


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open (or create) the SQLite database and apply migrations."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    _apply_migrations(conn)
    return conn


def store_run(conn: sqlite3.Connection, meta: RunMetadata) -> None:
    """Insert or replace a run record."""
    conn.execute(
        """
        INSERT OR REPLACE INTO runs
        (run_id, simulator, commit_sha, timestamp, total_tests, failed_tests,
         passed_tests, skipped_tests, source_path, parse_warnings, extra)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            meta.run_id,
            meta.simulator,
            meta.commit_sha,
            meta.timestamp.isoformat() if meta.timestamp else None,
            meta.total_tests,
            meta.failed_tests,
            meta.passed_tests,
            meta.skipped_tests,
            meta.source_path,
            json.dumps(meta.parse_warnings),
            json.dumps(meta.extra),
        ),
    )
    conn.commit()


def store_failures(conn: sqlite3.Connection, failures: list[FailureRecord]) -> None:
    """Insert or replace failure records. Does NOT store ground_truth_bug_ids."""
    rows = []
    for rec in failures:
        rows.append((
            rec.failure_id,
            rec.run_id,
            rec.test_name,
            rec.seed,
            rec.commit_sha,
            rec.timestamp.isoformat() if rec.timestamp else None,
            rec.simulator,
            rec.error_class,
            rec.first_error_message,
            rec.normalized_signature,
            json.dumps(rec.context_lines),
            rec.source_file,
            rec.source_line,
            rec.simulation_time,
            rec.simulation_time_unit,
            json.dumps(rec.mentioned_files),
            json.dumps(rec.mentioned_modules),
            rec.exit_code,
            json.dumps(rec.parse_warnings),
            rec.raw_evidence_reference,
            json.dumps({k: {"source": v.source.value, "note": v.note}
                        for k, v in rec.provenance.items()}),
        ))
    conn.executemany(
        """
        INSERT OR REPLACE INTO failures
        (failure_id, run_id, test_name, seed, commit_sha, timestamp, simulator,
         error_class, first_error_message, normalized_signature, context_lines,
         source_file, source_line, simulation_time, simulation_time_unit,
         mentioned_files, mentioned_modules, exit_code, parse_warnings,
         raw_evidence_reference, provenance)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.commit()


def load_failures(conn: sqlite3.Connection, run_id: str) -> list[FailureRecord]:
    """Load all failure records for a run_id."""
    rows = conn.execute(
        "SELECT * FROM failures WHERE run_id = ?", (run_id,)
    ).fetchall()
    result = []
    for row in rows:
        rec = FailureRecord(
            failure_id=row["failure_id"],
            test_name=row["test_name"],
            seed=row["seed"],
            run_id=row["run_id"],
            commit_sha=row["commit_sha"],
            simulator=row["simulator"],
            error_class=row["error_class"],
            first_error_message=row["first_error_message"],
            normalized_signature=row["normalized_signature"],
            context_lines=json.loads(row["context_lines"] or "[]"),
            source_file=row["source_file"],
            source_line=row["source_line"],
            simulation_time=row["simulation_time"],
            simulation_time_unit=row["simulation_time_unit"],
            mentioned_files=json.loads(row["mentioned_files"] or "[]"),
            mentioned_modules=json.loads(row["mentioned_modules"] or "[]"),
            exit_code=row["exit_code"],
            parse_warnings=json.loads(row["parse_warnings"] or "[]"),
            raw_evidence_reference=row["raw_evidence_reference"],
        )
        result.append(rec)
    return result


def list_runs(conn: sqlite3.Connection) -> list[dict]:
    """Return a list of all stored runs (metadata only)."""
    rows = conn.execute("SELECT * FROM runs ORDER BY imported_at DESC").fetchall()
    return [dict(r) for r in rows]
