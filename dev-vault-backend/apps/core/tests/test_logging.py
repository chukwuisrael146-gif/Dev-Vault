import logging

from apps.core.logging import REDACTED, RedactingFilter, redact_value


def test_redaction_removes_credentials_recursively() -> None:
    value = {
        "authorization": "Bearer eyJ.header.payload",
        "nested": {"api_key": "dv_live_identifier_secretvalue"},
    }

    assert redact_value(value) == {
        "authorization": REDACTED,
        "nested": {"api_key": REDACTED},
    }


def test_logging_filter_redacts_formatted_arguments() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="credential=%s",
        args=("dv_test_identifier_secretvalue",),
        exc_info=None,
    )

    RedactingFilter().filter(record)

    assert "secretvalue" not in record.getMessage()
    assert REDACTED in record.getMessage()
