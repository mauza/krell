"""Tests for rating tool plugin."""

import pytest
import tempfile
import os
from plugins.rating_tool import create_rating_async, get_ratings_async
from plugins.entity_tool import create_entity_async
from plugins.event_tool import create_event_async
from database.db import Database


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
async def test_create_rating_for_entity(temp_db):
    """Test create_rating for an entity."""
    db = Database(temp_db)
    await db.init_db()

    # Create entity to rate
    entity_result = await create_entity_async(db, "place", "Italian Restaurant")

    result = await create_rating_async(
        db,
        target_type="entity",
        target_id=entity_result["entity_id"],
        category="meal",
        score=5,
        notes="Amazing pasta!",
    )

    assert result["success"] is True
    assert "rating_id" in result


@pytest.mark.asyncio
async def test_create_rating_for_event(temp_db):
    """Test create_rating for an event."""
    db = Database(temp_db)
    await db.init_db()

    # Create event to rate
    event_result = await create_event_async(db, "Team Meeting")

    result = await create_rating_async(
        db,
        target_type="event",
        target_id=event_result["event_id"],
        category="meeting",
        score=4,
        notes="Very productive",
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_get_ratings_by_target(temp_db):
    """Test getting ratings for a specific target."""
    db = Database(temp_db)
    await db.init_db()

    entity_result = await create_entity_async(db, "place", "Gym")
    entity_id = entity_result["entity_id"]

    # Create ratings
    await create_rating_async(db, "entity", entity_id, "workout", 5)
    await create_rating_async(db, "entity", entity_id, "workout", 4)

    # Get ratings
    result = await get_ratings_async(db, target_type="entity", target_id=entity_id)
    assert result["statistics"]["count"] >= 2


@pytest.mark.asyncio
async def test_get_ratings_by_category(temp_db):
    """Test getting ratings by category."""
    db = Database(temp_db)
    await db.init_db()

    entity1 = await create_entity_async(db, "place", "Restaurant 1")
    entity2 = await create_entity_async(db, "place", "Restaurant 2")

    await create_rating_async(db, "entity", entity1["entity_id"], "meal", 5)
    await create_rating_async(db, "entity", entity2["entity_id"], "meal", 4)

    # Get all meal ratings
    result = await get_ratings_async(db, category="meal")
    assert result["statistics"]["count"] >= 2
    assert result["statistics"]["category"] == "meal"
