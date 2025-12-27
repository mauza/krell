"""
Entity tool plugin for Krell.

Provides tools for managing people, places, and things.
"""

from strands import tool
from database.db import Database
import json


# Helper functions for async database operations


async def create_entity_async(
    db: Database,
    entity_type: str,
    name: str,
    description: str = None,
    metadata: dict = None,
) -> dict:
    """Create an entity (async helper)."""
    entity_id = await db.create_entity(entity_type, name, description, metadata)
    return {
        "success": True,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "name": name,
    }


async def update_entity_async(
    db: Database, entity_id: str, description: str = None, metadata: dict = None
) -> dict:
    """Update an entity (async helper)."""
    success = await db.update_entity(entity_id, description, metadata)
    return {"success": success, "entity_id": entity_id}


async def search_entities_async(
    db: Database, query: str = None, entity_type: str = None, limit: int = 10
) -> dict:
    """Search entities (async helper)."""
    results = await db.search_entities(query, entity_type, limit)

    # Format for conversational response
    if not results:
        return {"entities": [], "message": "No entities found matching your search."}

    # Parse metadata from JSON strings
    for entity in results:
        if entity.get("metadata"):
            try:
                entity["metadata"] = json.loads(entity["metadata"])
            except (json.JSONDecodeError, TypeError):
                entity["metadata"] = {}

    return {
        "entities": results,
        "count": len(results),
        "message": f"Found {len(results)} {'entity' if len(results) == 1 else 'entities'}.",
    }


# Strands @tool decorated functions


@tool
def create_entity(
    entity_type: str, name: str, description: str = None, metadata: dict = None
) -> dict:
    """
    Create a new person, place, or thing to track.

    Use this when the user mentions new people, locations, or items worth remembering.

    Args:
        entity_type: Type of entity - 'person', 'place', or 'thing'
        name: Name of the entity
        description: Optional description or context
        metadata: Optional dict with additional info (e.g., {relationship: "friend", phone: "555-1234"})

    Returns:
        Success status and entity ID
    """
    import asyncio
    from config import config

    if entity_type not in ("person", "place", "thing"):
        return {
            "error": f"Invalid entity type: {entity_type}. Must be 'person', 'place', or 'thing'."
        }

    db = Database(config.database_path)
    result = asyncio.run(
        create_entity_async(db, entity_type, name, description, metadata)
    )
    return result


@tool
def update_entity(
    entity_id: str, description: str = None, metadata: dict = None
) -> dict:
    """
    Update an existing entity with new information.

    Use this when you learn new details about a person, place, or thing.

    Args:
        entity_id: ID of the entity to update
        description: New or updated description
        metadata: New or updated metadata (replaces existing)

    Returns:
        Success status
    """
    import asyncio
    from config import config

    db = Database(config.database_path)
    result = asyncio.run(update_entity_async(db, entity_id, description, metadata))
    return result


@tool
def search_entities(
    query: str = None, entity_type: str = None, limit: int = 10
) -> dict:
    """
    Search for people, places, or things.

    Use this when the user asks about someone or something you've tracked before.

    Args:
        query: Search term (searches name and description)
        entity_type: Filter by type - 'person', 'place', or 'thing'
        limit: Maximum results (default: 10)

    Returns:
        List of matching entities with conversational summary
    """
    import asyncio
    from config import config

    db = Database(config.database_path)
    result = asyncio.run(search_entities_async(db, query, entity_type, limit))
    return result
