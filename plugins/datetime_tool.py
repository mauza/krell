"""
Date/Time tool plugin for Krell.

Provides current date/time information for agent context.
"""

from datetime import datetime
from strands import tool
import pytz
from pytz.exceptions import UnknownTimeZoneError


@tool
def get_current_datetime(timezone: str = "UTC") -> dict:
    """
    Get the current date and time in multiple formats.

    Use this tool when you need to reference the current date or time
    in your responses, such as "today", "this week", or time-based context.

    Args:
        timezone: Timezone name (e.g., "UTC", "America/New_York", "Europe/London")

    Returns:
        Dictionary containing ISO format, readable format, and timezone
    """
    try:
        if timezone == "UTC":
            tz = pytz.UTC
        else:
            tz = pytz.timezone(timezone)
    except pytz.exceptions.UnknownTimeZoneError:
        return {
            "error": f"Unknown timezone: {timezone}. Use format like 'America/New_York' or 'Europe/London'."
        }

    now = datetime.now(tz)

    return {
        "iso_format": now.isoformat(),
        "readable_format": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": timezone,
        "timestamp": now.timestamp(),
    }
