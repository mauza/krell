"""Integration tests for the entity-based information system."""

import pytest
import tempfile
import os
from database.db import Database
from core.agent import KrellAgent
from core.plugin_loader import load_plugins


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_full_entity_workflow(temp_db):
    """Test complete workflow: create entity, event, journal, rating."""
    db = Database(temp_db)
    await db.init_db()

    # Create person entity
    person_id = await db.create_entity("person", "Alice", "Friend from college")
    assert person_id is not None

    # Create place entity
    place_id = await db.create_entity("place", "Downtown Cafe")
    assert place_id is not None

    # Create event with participants and location
    event_id = await db.create_event(
        name="Coffee Chat",
        description="Caught up with Alice",
        participants=[person_id],
        location=place_id,
    )
    assert event_id is not None

    # Create journal entry about the event
    journal_id = await db.create_journal(
        content="Had a wonderful conversation with Alice about life and work",
        related_entities=[person_id, place_id],
        related_event_id=event_id,
    )
    assert journal_id is not None

    # Rate the event
    rating_id = await db.create_rating(
        target_type="event",
        target_id=event_id,
        category="social",
        score=5,
        notes="Great time!",
    )
    assert rating_id is not None

    # Search for entity
    results = await db.search_entities(query="Alice")
    assert len(results) == 1
    assert results[0]["name"] == "Alice"

    # Search for events with Alice
    events = await db.search_events(participant_id=person_id)
    assert len(events) == 1
    assert events[0]["name"] == "Coffee Chat"

    # Search journals mentioning Alice
    journals = await db.search_journals(entity_id=person_id)
    assert len(journals) == 1
    assert "Alice" in journals[0]["content"]

    # Get ratings for the event
    ratings_result = await db.get_ratings_by_target("event", event_id)
    assert ratings_result["statistics"]["count"] == 1
    assert ratings_result["statistics"]["average"] == 5.0


@pytest.mark.asyncio
async def test_agent_has_all_tools(temp_db):
    """Test that Sarah agent has access to all entity tools."""
    db = Database(temp_db)
    await db.init_db()

    tools = load_plugins()

    # Verify we have the core tools
    tool_names = [t.__name__ for t in tools]

    required_tools = [
        "create_entity",
        "search_entities",
        "create_event",
        "search_events",
        "create_journal",
        "search_journals",
        "create_rating",
        "get_ratings",
    ]

    for tool_name in required_tools:
        assert tool_name in tool_names, f"Missing required tool: {tool_name}"


@pytest.mark.asyncio
async def test_entity_relationship_queries(temp_db):
    """Test querying relationships between entities."""
    db = Database(temp_db)
    await db.init_db()

    # Create people
    alice_id = await db.create_entity("person", "Alice")
    bob_id = await db.create_entity("person", "Bob")

    # Create shared event
    event_id = await db.create_event(
        name="Team Meeting", participants=[alice_id, bob_id]
    )

    # Find events Alice attended
    alice_events = await db.search_events(participant_id=alice_id)
    assert len(alice_events) == 1

    # Find events Bob attended
    bob_events = await db.search_events(participant_id=bob_id)
    assert len(bob_events) == 1

    # Both should return the same event
    assert alice_events[0]["id"] == bob_events[0]["id"]
