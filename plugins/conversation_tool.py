"""
Conversation search tool plugin for Krell.

Provides tools for searching past conversations.
"""

from strands import tool
from database.db import Database


# Helper function for async database operations
async def search_past_conversations_async(
    db: Database, query: str, limit: int = 5
) -> dict:
    """
    Search past conversations for relevant context (async helper).

    Args:
        db: Database instance
        query: Search query (simple text match for MVP)
        limit: Maximum number of results

    Returns:
        List of relevant conversation snippets
    """
    results = await db.search_conversations(query, limit)
    return {"results": results}


# Strands @tool decorated function


@tool
def search_past_conversations(query: str, limit: int = 5) -> dict:
    """
    Search past conversations for relevant context.

    Use this tool when the user references past conversations, asks about
    previous topics discussed, or when you need context from earlier interactions.

    This performs a simple text search across conversation titles and message content.

    Args:
        query: Search query string (e.g., "vacation planning", "AI discussion")
        limit: Maximum number of conversation results to return (default: 5)

    Returns:
        List of relevant conversation snippets with titles and message previews
    """
    import asyncio
    from config import config

    # Get database instance from config
    db = Database(config.database_path)

    # Run async operation
    result = asyncio.run(search_past_conversations_async(db, query, limit))

    return result
