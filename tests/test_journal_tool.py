"""Tests for journal tool plugin."""

import pytest
from plugins.journal_tool import create_journal, search_journals


def test_create_journal_tool():
    """Test create_journal tool function."""
    result = create_journal(
        content="Had a great discussion about design patterns today"
    )

    assert result["success"] is True
    assert "journal_id" in result


def test_create_journal_with_relations():
    """Test create_journal with related entities and events."""
    from plugins.entity_tool import create_entity
    from plugins.event_tool import create_event

    # Create related entity and event
    entity_result = create_entity("person", "John Doe")
    event_result = create_event("Coffee Meeting")

    result = create_journal(
        content="Met with John for coffee",
        related_entities=[entity_result["entity_id"]],
        related_event_id=event_result["event_id"],
    )

    assert result["success"] is True


def test_search_journals_tool():
    """Test search_journals tool function."""
    # Create test journal
    create_journal("Finished reading an amazing book today")

    # Search
    result = search_journals(query="book")
    assert len(result["journals"]) >= 1
    assert any("book" in j["content"] for j in result["journals"])
