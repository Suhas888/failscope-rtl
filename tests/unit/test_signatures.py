"""Unit tests for B1 signature normalisation."""
import pytest
from failscope.signatures import (
    NormalisationConfig,
    normalise_message,
    compute_b0_key,
    compute_b1_signature,
)
from failscope.models import FailureRecord


class TestNormaliseMessage:
    def test_none_returns_none(self):
        assert normalise_message(None) is None

    def test_empty_string(self):
        result = normalise_message("")
        assert result == ""

    def test_replaces_timestamp(self):
        msg = "Error at 2024-01-15T12:30:45Z: assertion failed"
        result = normalise_message(msg)
        assert "<TIMESTAMP>" in result
        assert "2024-01-15" not in result

    def test_replaces_hex_address(self):
        msg = "%Error: addr=0xDEADBEEF fault"
        result = normalise_message(msg)
        assert "<ADDR>" in result
        assert "0xDEADBEEF" not in result

    def test_replaces_seed(self):
        msg = "seed=12345678 test failed"
        result = normalise_message(msg)
        assert "<SEED>" in result
        assert "12345678" not in result

    def test_replaces_long_path(self):
        msg = "%Error: /home/user/project/counter.v:42: assertion"
        result = normalise_message(msg)
        assert "<PATH>" in result
        assert "/home/user/project" not in result

    def test_replaces_large_number(self):
        msg = "timeout at time 10000ns"
        result = normalise_message(msg)
        # 10000 is >= 4 digits
        assert "10000" not in result

    def test_preserves_small_numbers(self):
        """Small numbers (< 4 digits) should NOT be replaced — assertion diffs matter."""
        msg = "count=7 expected=8"
        result = normalise_message(msg)
        assert "7" in result
        assert "8" in result

    def test_normalises_whitespace(self):
        msg = "Error:  assertion   failed   at  line"
        result = normalise_message(msg)
        assert "  " not in result

    def test_disable_timestamp_replacement(self):
        cfg = NormalisationConfig(replace_timestamps=False)
        msg = "Error at 2024-01-15T12:30:45Z: assertion"
        result = normalise_message(msg, cfg)
        assert "2024-01-15" in result

    def test_does_not_erase_operator_differences(self):
        """Distinct assertion messages should still be distinct after normalisation."""
        msg1 = "%Error: count == expected"
        msg2 = "%Error: count != expected"
        n1 = normalise_message(msg1)
        n2 = normalise_message(msg2)
        assert n1 != n2

    def test_unicode_preserved(self):
        msg = "Ошибка: assertion failed ♦"
        result = normalise_message(msg)
        assert "Ошибка" in result

    def test_idempotent(self):
        msg = "%Error: counter.v:42: assertion failed"
        r1 = normalise_message(msg)
        r2 = normalise_message(r1)
        assert r1 == r2


class TestB0Key:
    def test_exact_message_returned(self):
        rec = FailureRecord(first_error_message="%Error: counter.v:42: assertion")
        key = compute_b0_key(rec)
        assert key == "%Error: counter.v:42: assertion"

    def test_fallback_when_no_message(self):
        rec = FailureRecord(error_class="assertion", test_name="test_foo")
        key = compute_b0_key(rec)
        assert "assertion" in key
        assert "test_foo" in key

    def test_sentinel_when_all_unavailable(self):
        rec = FailureRecord()
        key = compute_b0_key(rec)
        assert key == "__NO_ERROR_MESSAGE__"


class TestB1Signature:
    def test_different_seeds_same_signature(self):
        """Two records with same error but different seeds should normalise to same sig."""
        rec1 = FailureRecord(first_error_message="seed=11111111 assertion failed")
        rec2 = FailureRecord(first_error_message="seed=22222222 assertion failed")
        assert compute_b1_signature(rec1) == compute_b1_signature(rec2)

    def test_distinct_errors_distinct_signatures(self):
        rec1 = FailureRecord(first_error_message="%Error: count == expected")
        rec2 = FailureRecord(first_error_message="UVM_FATAL [TIMEOUT]: watchdog expired")
        assert compute_b1_signature(rec1) != compute_b1_signature(rec2)

    def test_fallback_when_no_message(self):
        rec = FailureRecord(error_class="fatal")
        sig = compute_b1_signature(rec)
        assert sig  # non-empty
