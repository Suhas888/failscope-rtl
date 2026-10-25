"""
Feature extraction for B2/B3 clustering.

B2 features: TF-IDF over first_error_message + bounded context lines.
B3 features: B2 + structured metadata features.

Ground-truth labels are never included in any feature.
"""

from __future__ import annotations

from typing import Optional, Any
import re

import numpy as np


# Maximum context lines to include in TF-IDF text
_MAX_CONTEXT = 5

# Field values that indicate "unavailable" — excluded from numeric features
_NA_SENTINEL = None


def build_tfidf_text(record) -> str:
    """
    Build the text representation for TF-IDF vectorisation.

    Uses first_error_message + up to _MAX_CONTEXT context lines.
    Raw evidence is used; normalisation is handled inside TF-IDF.
    """
    parts: list[str] = []
    if record.first_error_message:
        parts.append(record.first_error_message)
    # Prepend normalised signature if available (adds signal without duplication)
    if record.normalized_signature and record.normalized_signature != record.first_error_message:
        parts.append(record.normalized_signature)
    # Bounded context
    for line in record.context_lines[:_MAX_CONTEXT]:
        if line.strip():
            parts.append(line.strip())
    return " ".join(parts) if parts else "__EMPTY__"


def extract_structured_features(records: list) -> np.ndarray:
    """
    Extract a structured feature matrix for B3.

    Features per record (all normalised to [0, 1] or one-hot):
      - error_class indicator (fatal=1, error=0.5, uvm_error=0.7, other=0.2)
      - has_source_file (0/1)
      - has_simulation_time (0/1)
      - has_seed (0/1)
      - mentioned_file_count (capped at 5, normalised)
      - mentioned_module_count (capped at 5, normalised)
      - simulator_hash (one-hot within known simulators)

    Missing values are represented as 0.0 (absent/unknown).

    NOTE: ground_truth_bug_ids are never accessed here.
    """
    n = len(records)
    if n == 0:
        return np.zeros((0, 10), dtype=np.float32)

    known_simulators = ["verilator", "cocotb", "uvm"]
    n_sims = len(known_simulators)
    n_features = 6 + n_sims  # base features + simulator one-hot

    mat = np.zeros((n, n_features), dtype=np.float32)

    error_class_score = {
        "fatal": 1.0, "uvm_fatal": 1.0,
        "uvm_error": 0.7,
        "error": 0.5, "assertion": 0.4,
        "failure": 0.3,
    }

    for i, rec in enumerate(records):
        ec = (rec.error_class or "").lower()
        mat[i, 0] = error_class_score.get(ec, 0.2)
        mat[i, 1] = 1.0 if rec.source_file else 0.0
        mat[i, 2] = 1.0 if rec.simulation_time else 0.0
        mat[i, 3] = 1.0 if rec.seed else 0.0
        mat[i, 4] = min(len(rec.mentioned_files), 5) / 5.0
        mat[i, 5] = min(len(rec.mentioned_modules), 5) / 5.0
        sim = (rec.simulator or "").lower()
        for j, known in enumerate(known_simulators):
            if sim == known:
                mat[i, 6 + j] = 1.0
                break

    return mat


def build_cofailure_matrix(records: list, run_group_key: str = "run_id") -> Optional[np.ndarray]:
    """
    Build a co-failure similarity matrix for B3.

    Two failures are co-occurring if they belong to the same run_id.
    Returns a symmetric [n x n] matrix where entry (i,j) = 1 if
    failures i and j share at least one run_id, else 0.

    Returns None if all records have the same or unknown run_id
    (degenerate: no discriminating signal).
    """
    n = len(records)
    if n == 0:
        return None

    run_ids = [getattr(r, run_group_key, None) for r in records]
    unique_runs = set(r for r in run_ids if r is not None)

    if len(unique_runs) <= 1:
        return None  # No cross-run signal

    # Build set of run_ids per record
    record_runs: list[set] = [
        {rid} if rid is not None else set() for rid in run_ids
    ]

    mat = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i, n):
            shared = record_runs[i] & record_runs[j]
            val = 1.0 if shared else 0.0
            mat[i, j] = mat[j, i] = val

    return mat
