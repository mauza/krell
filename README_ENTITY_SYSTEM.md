# Sarah Entity-Based Information System

## Overview

Sarah now uses an entity-based information system to track and recall information about your life. This system replaces the previous simple journal/rating system with a composable model that connects people, places, things, events, and experiences.

## Core Concepts

### Entities
Track people, places, and things:
- **People**: Friends, colleagues, family members
- **Places**: Locations, venues, addresses
- **Things**: Items, objects worth remembering

### Events
Track meetings, gatherings, appointments, and experiences:
- Can link to participants (people entities)
- Can link to locations (place entities)
- Can be rated

### Journals
Reflections and diary-like entries:
- Can reference multiple entities
- Can be linked to events
- Searchable by content or related entities

### Ratings
Score entities or events on a 1-5 scale:
- Track categories (meal, meeting, workout, mood, etc.)
- Get statistics (average, count)
- Filter by category or target

## Using the System

### Sarah's Behavior

Sarah now acts as a **scribe and information assistant** rather than a conversational companion. She will:

1. **Proactively capture information** when you mention people, places, or experiences
2. **Suggest ratings** when you express sentiment ("That was amazing!" → "Want to rate it?")
3. **Ask for missing details** when entities are mentioned again with incomplete information
4. **Retrieve and connect information** conversationally when you ask questions

### Example Interactions

**Creating entities:**
- "I met John at the tech conference" → Sarah creates person (John) and event (tech conference)
- "Had lunch at the new Italian place" → Sarah creates place (Italian restaurant)

**Rating experiences:**
- "That meeting was terrible" → Sarah: "Would you like to rate that meeting?"
- "Amazing workout today!" → Sarah: "Sounds great! Want to rate it?"

**Retrieving information:**
- "What do I know about John?" → Sarah summarizes all info about John (when met, events attended, etc.)
- "Show me all my meal ratings" → Sarah shows ratings with statistics

## Database Schema

### Tables

**entities:**
- People, places, things
- Fields: type, name, description, metadata (JSON)

**events:**
- Meetings, gatherings, experiences
- Fields: name, description, date, participants (JSON), location

**journals:**
- Reflections and diary entries
- Fields: content, related_entities (JSON), related_event_id

**ratings:**
- 1-5 scores for entities or events
- Fields: target_type, target_id, category, score, notes

## Migration

If you have an existing Sarah database, run the migration script:

```bash
cd backend
python migrate_database.py ./data/sarah.db
```

This will:
- Backup your existing database
- Create new tables (entities, events, journals, ratings)
- Migrate existing journal_entries and ratings
- Preserve all conversation history

## Development

### Running Tests

```bash
cd backend
pytest tests/test_database.py -v
pytest tests/test_entity_tool.py -v
pytest tests/test_event_tool.py -v
pytest tests/test_journal_tool.py -v
pytest tests/test_rating_tool.py -v
pytest tests/test_integration_entity_system.py -v
```

### Adding New Entity Types

To add new entity types (beyond person/place/thing):
1. Update database constraint in `database/migrations/001_entity_system.sql`
2. Update validation in `database/db.py` `create_entity` method
3. Update `entity_tool.py` docstrings

### Tool Development

All tools follow this pattern:
1. Async helper function (does database work)
2. `@tool` decorated function (Strands tool, calls helper via asyncio.run)
3. Clear docstring explaining when to use the tool

## Architecture Decisions

### Why Explicit Schema (Not Generic Relationships)?

We chose explicit tables (entities, events, journals, ratings) over a fully generic relationship system because:
- Simpler to query and reason about
- Easier for LLM to understand and use
- Better performance for common queries
- Can still be extended with metadata JSON fields

### Why JSON for Participants/Related Entities?

We use JSON arrays for relationships because:
- SQLite has good JSON support
- Simpler than many-to-many join tables
- Flexible for the AI to work with
- Sufficient for our use case (not millions of relationships)

### Future Enhancements

Potential future improvements:
- Sentiment analysis for automatic rating suggestions
- Probe history tracking (avoid repeated questions)
- Full-text search with relevance ranking
- Entity mention frequency tracking
- Automatic entity extraction from conversations