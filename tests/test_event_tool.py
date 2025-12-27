"""Tests for event tool plugin."""

import pytest
from plugins.event_tool import create_event, search_events


def test_create_event_tool():
    """Test create_event tool function."""
    result = create_event(
        name="Coffee Meeting",
        description="Discussed design project",
        event_date="2025-12-12T10:00:00",
    )

    assert result["success"] is True
    assert "event_id" in result
    assert result["name"] == "Coffee Meeting"


def test_search_events_tool():
    """Test search_events tool function."""
    # Create test event
    create_event(name="Tech Conference", description="Annual technology event")

    # Search for event
    result = search_events(query="conference")
    assert len(result["events"]) >= 1
    assert any(e["name"] == "Tech Conference" for e in result["events"])
