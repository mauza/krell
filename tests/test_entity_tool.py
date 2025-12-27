"""Tests for entity tool plugin."""

import pytest
import tempfile
import os
from plugins.entity_tool import (
    create_entity_async,
    update_entity_async,
    search_entities_async,
)
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
async def test_create_entity_tool(temp_db):
    """Test create_entity tool function."""
    db = Database(temp_db)
    await db.init_db()

    result = await create_entity_async(
        db,
        entity_type="person",
        name="John Doe",
        description="Designer from conference",
        metadata={"relationship": "colleague"},
    )

    assert result["success"] is True
    assert "entity_id" in result
    assert result["entity_type"] == "person"
    assert result["name"] == "John Doe"


@pytest.mark.asyncio
async def test_update_entity_tool(temp_db):
    """Test update_entity tool function."""
    db = Database(temp_db)
    await db.init_db()

    # Create entity first
    create_result = await create_entity_async(db, "person", "Jane Smith")
    entity_id = create_result["entity_id"]

    # Update it
    result = await update_entity_async(
        db,
        entity_id=entity_id,
        description="Product manager at TechCo",
        metadata={"relationship": "colleague", "company": "TechCo"},
    )

    assert result["success"] is True
    assert result["entity_id"] == entity_id


@pytest.mark.asyncio
async def test_search_entities_tool(temp_db):
    """Test search_entities tool function."""
    db = Database(temp_db)
    await db.init_db()

    # Create test entities
    await create_entity_async(db, "person", "John Doe", "Designer")
    await create_entity_async(db, "place", "Coffee Shop", "Downtown cafe")

    # Search for person
    result = await search_entities_async(db, query="John")
    assert len(result["entities"]) >= 1
    assert any(e["name"] == "John Doe" for e in result["entities"])

    # Search by type
    result = await search_entities_async(db, entity_type="place")
    assert len(result["entities"]) >= 1
    assert all(e["type"] == "place" for e in result["entities"])
