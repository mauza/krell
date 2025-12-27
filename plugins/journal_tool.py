"""
Journal tool plugin for Krell.

Provides tools for creating and searching journal entries.
"""

from strands import tool
from database.db import Database
import json


# Helper functions for async database operations


async def create_journal_async(
    db: Database,
    content: str,
    related_entities: list = None,
    related_event_id: str = None,
) -> dict:
    """Create a journal entry (async helper)."""
    journal_id = await db.create_journal(content, related_entities, related_event_id)
    return {"success": True, "journal_id": journal_id}


async def search_journals_async(
    db: Database,
    query: str = None,
    entity_id: str = None,
    event_id: str = None,
    limit: int = 10,
) -> dict:
    """Search journals (async helper)."""
    results = await db.search_journals(query, entity_id, event_id, limit)

    if not results:
        return {"journals": [], "message": "No journal entries found."}

    # Parse JSON fields
    for journal in results:
        if journal.get("related_entities"):
            try:
                journal["related_entities"] = json.loads(journal["related_entities"])
            except (json.JSONDecodeError, TypeError):
                journal["related_entities"] = []

    return {
        "journals": results,
        "count": len(results),
        "message": f"Found {len(results)} journal {'entry' if len(results) == 1 else 'entries'}.",
    }


# Strands @tool decorated functions


@tool
def create_journal(
    content: str, related_entities: list = None, related_event_id: str = None
) -> dict:
    """
    Create a journal entry for reflections and experiences.

    Use this when the user shares meaningful moments, reflections, or experiences
    worth remembering.

    Args:
        content: Journal entry content
        related_entities: List of entity IDs mentioned in this entry
        related_event_id: Optional event ID this journal is about

    Returns:
        Success status and journal ID
    """
    import asyncio
    from config import config

    db = Database(config.database_path)
    result = asyncio.run(
        create_journal_async(db, content, related_entities, related_event_id)
    )
    return result


@tool
def search_journals(
    query: str = None, entity_id: str = None, event_id: str = None, limit: int = 10
) -> dict:
    """
    Search journal entries.

    Use this when the user asks about past reflections, experiences, or moments.

    Args:
        query: Search term (searches content)
        entity_id: Filter by related entity ID
        event_id: Filter by related event ID
        limit: Maximum results (default: 10)

    Returns:
        List of matching journal entries with conversational summary
    """
    import asyncio
    from config import config

    db = Database(config.database_path)
    result = asyncio.run(search_journals_async(db, query, entity_id, event_id, limit))
    return result
