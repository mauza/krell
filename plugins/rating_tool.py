"""
Rating tool plugin for Krell.

Provides tools for rating entities and events on a 1-5 scale.
"""

from strands import tool
from database.db import Database


# Helper functions for async database operations


async def create_rating_async(
    db: Database,
    target_type: str,
    target_id: str,
    category: str,
    score: int,
    notes: str = None,
) -> dict:
    """Create a rating (async helper)."""
    rating_id = await db.create_rating(target_type, target_id, category, score, notes)
    return {
        "success": True,
        "rating_id": rating_id,
        "score": score,
        "category": category,
    }


async def get_ratings_async(
    db: Database,
    target_type: str = None,
    target_id: str = None,
    category: str = None,
    limit: int = 50,
) -> dict:
    """Get ratings (async helper)."""
    if target_type and target_id:
        # Get ratings for specific target
        result = await db.get_ratings_by_target(target_type, target_id, limit)
    elif category:
        # Get ratings by category
        result = await db.get_ratings_by_category(category, limit)
    else:
        return {"error": "Must provide either (target_type and target_id) or category"}

    return result


# Strands @tool decorated functions


@tool
def create_rating(
    target_type: str, target_id: str, category: str, score: int, notes: str = None
) -> dict:
    """
    Rate an entity or event on a 1-5 scale.

    Use this when the user expresses sentiment about something (meal, meeting, workout, etc.)
    or explicitly asks to rate something.

    Common categories: meal, meeting, workout, mood, entertainment, sleep, productivity

    Args:
        target_type: 'entity' or 'event'
        target_id: ID of entity or event being rated
        category: Rating category (e.g., 'meal', 'meeting', 'workout')
        score: Rating score from 1 to 5 (1=poor, 5=excellent)
        notes: Optional notes about the rating

    Returns:
        Success status and rating ID
    """
    import asyncio
    from config import config

    if target_type not in ("entity", "event"):
        return {"error": "target_type must be 'entity' or 'event'"}

    if not 1 <= score <= 5:
        return {"error": "Score must be between 1 and 5"}

    db = Database(config.database_path)
    result = asyncio.run(
        create_rating_async(db, target_type, target_id, category, score, notes)
    )
    return result


@tool
def get_ratings(
    target_type: str = None,
    target_id: str = None,
    category: str = None,
    limit: int = 50,
) -> dict:
    """
    Get ratings with statistics.

    Use this when the user asks about past ratings or wants to see trends.
    Must provide either (target_type + target_id) OR category.

    Args:
        target_type: 'entity' or 'event' (required with target_id)
        target_id: ID of target (required with target_type)
        category: Rating category to filter by (alternative to target filters)
        limit: Maximum results (default: 50)

    Returns:
        List of ratings with statistics (count, average)
    """
    import asyncio
    from config import config

    db = Database(config.database_path)
    result = asyncio.run(get_ratings_async(db, target_type, target_id, category, limit))
    return result
