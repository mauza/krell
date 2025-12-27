import pytest
from plugins.datetime_tool import get_current_datetime


def test_get_current_datetime_returns_dict_with_iso_and_readable():
    result = get_current_datetime()

    assert isinstance(result, dict)
    assert "iso_format" in result
    assert "readable_format" in result
    assert "timezone" in result
    assert result["timezone"] == "UTC"

    # Verify ISO format is valid (basic check)
    assert "T" in result["iso_format"]  # ISO 8601 has T separator
    assert "2025" in result["iso_format"]  # Contains year


def test_get_current_datetime_with_different_timezone():
    result = get_current_datetime(timezone="America/New_York")

    assert isinstance(result, dict)
    assert result["timezone"] == "America/New_York"
    assert "EST" in result["readable_format"] or "EDT" in result["readable_format"]


def test_get_current_datetime_handles_invalid_timezone():
    result = get_current_datetime(timezone="Invalid/Timezone")

    assert "error" in result
    assert "Unknown timezone" in result["error"]
