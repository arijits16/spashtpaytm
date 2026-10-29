"""The PII-redaction filter is a section-13 non-negotiable, so it gets real tests."""

from __future__ import annotations

import json
import logging

import pytest

from app.logging import JsonFormatter, PiiRedactionFilter, redact


@pytest.mark.parametrize(
    ("raw", "must_not_contain", "must_contain"),
    [
        ("call me on +91 9876543210 please", "9876543210", "[MOBILE]"),
        ("pan is ABCPJ1234F ok", "ABCPJ1234F", "[PAN]"),
        ("aadhaar 1234 5678 4821", "5678", "[AADHAAR]"),
        ("mail sunita@example.com", "sunita@example.com", "[EMAIL]"),
        ("Authorization: Bearer eyJhbGciOi.abc123", "eyJhbGciOi", "[TOKEN]"),
        ("the otp is 482913", "482913", "[OTP]"),
    ],
)
def test_redact_removes_personal_data(raw: str, must_not_contain: str, must_contain: str) -> None:
    cleaned = redact(raw)

    assert must_not_contain not in cleaned
    assert must_contain in cleaned


def test_redact_keeps_uuids_intact() -> None:
    """Regression: a 6-digit run inside a UUID was being replaced with [OTP],
    which made user_id / journey_id untraceable in the demo logs."""
    uuid = "9a2814-9636-4c66-9bb5-392db7c725f1"

    assert redact(f"user_id={uuid}") == f"user_id={uuid}"
    assert redact("journey 123456-abcd-7890") == "journey 123456-abcd-7890"


def test_redact_still_catches_a_standalone_otp() -> None:
    """The UUID fix must not weaken the actual OTP rule."""
    assert "[OTP]" in redact("the otp is 482913")
    assert "[OTP]" in redact("Demo OTP: 482913.")


def test_redact_keeps_loan_facts_readable() -> None:
    """Rupee amounts and rates are product facts, not PII - they must survive."""
    cleaned = redact("EMI 4,600 for 12 months, total 55,200 at 18.67%")

    assert "4,600" in cleaned
    assert "55,200" in cleaned
    assert "18.67%" in cleaned


def test_filter_scrubs_the_message_and_extra_fields() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="user said %s",
        args=("my number is 9876543210",),
        exc_info=None,
    )
    record.transcript = "pan ABCPJ1234F"

    assert PiiRedactionFilter().filter(record) is True
    assert "9876543210" not in record.getMessage()
    assert record.transcript == "pan [PAN]"


def test_formatter_emits_one_json_object_with_extras() -> None:
    record = logging.LogRecord(
        name="spasht",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="turn done",
        args=(),
        exc_info=None,
    )
    record.journey_id = "abc"
    record.stt_ms = 820

    payload = json.loads(JsonFormatter().format(record))

    assert payload["msg"] == "turn done"
    assert payload["level"] == "INFO"
    assert payload["journey_id"] == "abc"
    assert payload["stt_ms"] == 820
    assert payload["ts"].endswith("+00:00")
