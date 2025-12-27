"""
Event tool plugin for Krell.

Provides tools for tracking events and experiences.
"""

from strands import tool
from database.db import Database
import json


# Helper functions for async database operations


async def create_event_async(
    db: Database,
    name: str,
    description: str = None,
    event_date: str = None,
    participants: list = None,
    location: str = None,
    metadata: dict = None,
) -> dict:
    """Create an event (async helper)."""
    event_id = await db.create_event(
        name, description, event_date, participants, location, metadata
    )
    return {"success": True, "event_id": event_id, "name": name}


async def search_events_async(
    db: Database, query: str = None, participant_id: str = None, limit: int = 10
) -> dict:
    """Search events (async helper)."""
    results = await db.search_events(query, participant_id, limit)

    if not results:
        return {"events": [], "message": "No events found matching your search."}

    # Parse JSON fields
    for event in results:
        if event.get("participants"):
            try:
                event["participants"] = json.loads(event["participants"])
            except (json.JSONDecodeError, TypeError):
                event["participants"] = []
        if event.get("metadata"):
            try:
                event["metadata"] = json.loads(event["metadata"])
            except (json.JSONDecodeError, TypeError):
                event["metadata"] = {}

    return {
        "events": results,
        "count": len(results),
        "message": f"Found {len(results)} {'event' if len(results) == 1 else 'events'}.",
    }


# Strands @tool decorated functions


@tool
def create_event(
    name: str,
    description: str = None,
    event_date: str = None,
    participants: list = None,
    location: str = None,
    metadata: dict = None,
) -> dict:
    """
    Create an event to track.

    Use this when the user mentions meetings, gatherings, appointments, or experiences.

    Args:
        name: Event name
        description: Optional description
        event_date: ISO format datetime (e.g., "2025-12-12T10:00:00")
        participants: List of entity IDs (people who attended/participated)
        location: Entity ID of place or free text location
        metadata: Optional additional information

    Returns:
        Success status and event ID
    """
    import asyncio
    from config import config

    db = Database(config.database_path)
    result = asyncio.run(
        create_event_async(
            db, name, description, event_date, participants, location, metadata
        )
    )
    return result


@tool
def search_events(
    query: str = None, participant_id: str = None, limit: int = 10
) -> dict:
    """
    Search for past events.

    Use this when the user asks about previous events, meetings, or experiences.

    Args:
        query: Search term (searches name and description)
        participant_id: Filter by participant entity ID
        limit: Maximum results (default: 10)

    Returns:
        List of matching events with conversational summary
    """
    import asyncio
    from config import config

    db = Database(config.database_path)
    result = asyncio.run(search_events_async(db, query, participant_id, limit))
    return result
