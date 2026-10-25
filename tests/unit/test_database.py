"""Unit tests for SQLite database storage module."""
import pytest
from pathlib import Path

from failscope.database import connect, store_run, store_failures, load_failures, list_runs
from failscope.models import FailureRecord, RunMetadata


class TestDatabase:
    def test_connect_creates_schema_and_version(self, tmp_path):
        db_file = tmp_path / "test.db"
        conn = connect(db_file)
        cur = conn.execute("SELECT version FROM schema_version")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 1

        # Check tables exist
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        assert "runs" in tables
        assert "failures" in tables
        assert "schema_version" in tables

    def test_store_and_list_runs(self, tmp_path):
        conn = connect(tmp_path / "test.db")
        meta = RunMetadata(
            run_id="run_123",
            simulator="verilator",
            commit_sha="abcdef12",
            total_tests=10,
            failed_tests=2,
            passed_tests=8,
            source_path="logs/run1.log",
            parse_warnings=["minor warning"],
        )
        store_run(conn, meta)

        runs = list_runs(conn)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "run_123"
        assert runs[0]["simulator"] == "verilator"
        assert runs[0]["failed_tests"] == 2

    def test_store_and_load_failures(self, tmp_path):
        conn = connect(tmp_path / "test.db")
        rec = FailureRecord(
            failure_id="fail_001",
            run_id="run_123",
            test_name="tb_counter_overflow",
            first_error_message="%Error: counter overflowed",
            normalized_signature="%Error: counter overflowed",
            raw_evidence_reference="run1.log:42",
            context_lines=["line 41", "line 42"],
            source_file="counter.v",
            source_line=42,
        )
        store_failures(conn, [rec])

        loaded = load_failures(conn, "run_123")
        assert len(loaded) == 1
        l0 = loaded[0]
        assert l0.failure_id == "fail_001"
        assert l0.test_name == "tb_counter_overflow"
        assert l0.first_error_message == "%Error: counter overflowed"
        assert l0.context_lines == ["line 41", "line 42"]
        assert l0.source_file == "counter.v"
        assert l0.source_line == 42

    def test_ground_truth_column_does_not_exist_in_db(self, tmp_path):
        """Privacy and leak-prevention: ground truth bug IDs must not be in schema."""
        conn = connect(tmp_path / "test.db")
        cols = [
            r[1] for r in conn.execute("PRAGMA table_info(failures)").fetchall()
        ]
        assert "ground_truth_bug_ids" not in cols
        assert "ground_truth" not in cols

    def test_idempotent_replace(self, tmp_path):
        conn = connect(tmp_path / "test.db")
        rec = FailureRecord(
            failure_id="fail_001",
            run_id="run_123",
            first_error_message="original error",
            raw_evidence_reference="run1.log:1",
        )
        store_failures(conn, [rec])

        # Store updated version with same failure_id
        rec_updated = FailureRecord(
            failure_id="fail_001",
            run_id="run_123",
            first_error_message="updated error",
            raw_evidence_reference="run1.log:1",
        )
        store_failures(conn, [rec_updated])

        loaded = load_failures(conn, "run_123")
        assert len(loaded) == 1
        assert loaded[0].first_error_message == "updated error"
