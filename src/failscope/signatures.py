"""
B1 normalisation signatures for FailScope RTL.

Deterministic, rule-based text normalisation used by the B1 clustering method.

Rules are applied in documented order and are configurable.
The goal is to collapse run-specific variation without erasing
meaningful error-class, assertion, or operator differences.

IMPORTANT: B0 exact-match uses raw first_error_message with NO normalisation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NormalisationConfig:
    """
    Configuration for B1 normalisation rules.

    All rules are enabled by default; each can be disabled independently.
    """
    replace_timestamps: bool = True
    replace_hex_addresses: bool = True
    replace_seeds: bool = True
    replace_paths: bool = True
    replace_variable_numbers: bool = True
    normalise_whitespace: bool = True

    # Custom placeholder strings
    timestamp_placeholder: str = "<TIMESTAMP>"
    hex_placeholder: str = "<ADDR>"
    seed_placeholder: str = "<SEED>"
    path_placeholder: str = "<PATH>"
    number_placeholder: str = "<N>"


# --- Compiled regexes ---

# Timestamps: 2024-01-01 12:00:00, 12:00:00.123, etc.
_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b"
    r"|\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b"
)

# Hex addresses / values: 0xDEADBEEF, DEADBEEF (8+ hex digits)
_HEX_RE = re.compile(r"\b0[xX][0-9A-Fa-f]+\b|\b[0-9A-Fa-f]{8,}\b")

# Seeds in common formats: "seed=12345", "SEED: 12345", "random seed 9876"
_SEED_RE = re.compile(
    r"(?:seed\s*[=:]\s*\d+|random\s+seed\s+\d+|\bseed\b\s+\d+)",
    re.IGNORECASE,
)

# File paths: /home/user/design/counter.v, C:\project\tb.sv
_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|/)(?:[\w.\-/\\]+)"
)

# Variable standalone integers NOT in meaningful error positions.
# We do NOT remove numbers from assertion messages to avoid merging distinct assertions.
# Only replace isolated large integers (>= 4 digits, optional unit) that appear to be run-specific,
# avoiding dates like YYYY-MM-DD.
_VARIABLE_NUM_RE = re.compile(r"(?<![-\d])\b\d{4,}(?:[a-zA-Z]{1,6})?\b(?!-\d{2})")

# Whitespace normalisation
_WHITESPACE_RE = re.compile(r"\s+")


def normalise_message(
    message: Optional[str],
    config: Optional[NormalisationConfig] = None,
) -> Optional[str]:
    """
    Apply B1 normalisation rules to a failure message.

    Returns None if input is None.
    Applies rules in a documented, deterministic order.
    """
    if message is None:
        return None

    cfg = config or NormalisationConfig()
    text = message

    if cfg.replace_timestamps:
        text = _TIMESTAMP_RE.sub(cfg.timestamp_placeholder, text)

    if cfg.replace_seeds:
        text = _SEED_RE.sub(cfg.seed_placeholder, text)

    if cfg.replace_hex_addresses:
        text = _HEX_RE.sub(cfg.hex_placeholder, text)

    if cfg.replace_paths:
        text = _PATH_RE.sub(cfg.path_placeholder, text)

    if cfg.replace_variable_numbers:
        # Replace 4+ digit numbers not already replaced
        text = _VARIABLE_NUM_RE.sub(cfg.number_placeholder, text)

    if cfg.normalise_whitespace:
        text = _WHITESPACE_RE.sub(" ", text).strip()

    return text


def compute_b0_key(record) -> str:
    """
    B0: exact first-error line, no normalisation.

    Returns the raw first_error_message, or a documented fallback
    if that field is unavailable.
    """
    if record.first_error_message:
        return record.first_error_message
    # Documented fallback: error_class + test_name
    fallback_parts = []
    if record.error_class:
        fallback_parts.append(f"class:{record.error_class}")
    if record.test_name:
        fallback_parts.append(f"test:{record.test_name}")
    if fallback_parts:
        return " | ".join(fallback_parts)
    return "__NO_ERROR_MESSAGE__"


def compute_b1_signature(
    record,
    config: Optional[NormalisationConfig] = None,
) -> str:
    """
    B1: normalised signature from first_error_message.

    If first_error_message is unavailable, falls back to error_class + test_name.
    """
    msg = normalise_message(record.first_error_message, config)
    if msg:
        return msg

    # Fallback: normalise error_class + test_name
    fallback_parts = []
    if record.error_class:
        fallback_parts.append(f"class:{record.error_class}")
    if record.test_name:
        fallback_parts.append(f"test:{record.test_name}")
    return " | ".join(fallback_parts) if fallback_parts else "__NO_SIGNATURE__"
