"""
Tests for the new database schema and operations.
Following TDD - these tests are written FIRST and should FAIL.
"""

import pytest
import aiosqlite
import tempfile
import os
from pathlib import Path


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
async def test_database_initialization_creates_tables(temp_db):
    """Test that database initialization creates all required tables"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    # Verify all tables exist
    async with aiosqlite.connect(temp_db) as conn:
        cursor = await conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' 
            ORDER BY name
        """)
        tables = [row[0] for row in await cursor.fetchall()]

    assert "conversations" in tables
    assert "messages" in tables
    assert "journal_entries" in tables
    assert "settings" in tables


@pytest.mark.asyncio
async def test_database_initialization_creates_indices(temp_db):
    """Test that database initialization creates required indices"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    # Verify indices exist
    async with aiosqlite.connect(temp_db) as conn:
        cursor = await conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' 
            ORDER BY name
        """)
        indices = [row[0] for row in await cursor.fetchall()]

    assert "idx_messages_conversation" in indices
    assert "idx_journal_created" in indices
    assert "idx_journal_type" in indices


@pytest.mark.asyncio
async def test_create_conversation(temp_db):
    """Test creating a new conversation"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    conversation_id = await db.create_conversation(title="Test Chat")

    assert conversation_id is not None
    assert isinstance(conversation_id, str)
    assert len(conversation_id) > 0


@pytest.mark.asyncio
async def test_get_conversation(temp_db):
    """Test retrieving a conversation by ID"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    conv_id = await db.create_conversation(title="My Conversation")
    conversation = await db.get_conversation(conv_id)

    assert conversation is not None
    assert conversation["id"] == conv_id
    assert conversation["title"] == "My Conversation"
    assert "created_at" in conversation
    assert "updated_at" in conversation


@pytest.mark.asyncio
async def test_list_conversations(temp_db):
    """Test listing all conversations"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    # Create multiple conversations
    await db.create_conversation(title="Chat 1")
    await db.create_conversation(title="Chat 2")
    await db.create_conversation(title="Chat 3")

    conversations = await db.list_conversations()

    assert len(conversations) == 3
    assert all("title" in c for c in conversations)


@pytest.mark.asyncio
async def test_update_conversation_title(temp_db):
    """Test updating a conversation's title"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    conv_id = await db.create_conversation(title="Old Title")
    success = await db.update_conversation_title(conv_id, "New Title")

    assert success is True

    conversation = await db.get_conversation(conv_id)
    assert conversation["title"] == "New Title"


@pytest.mark.asyncio
async def test_delete_conversation(temp_db):
    """Test deleting a conversation"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    conv_id = await db.create_conversation(title="To Delete")
    success = await db.delete_conversation(conv_id)

    assert success is True

    conversation = await db.get_conversation(conv_id)
    assert conversation is None


@pytest.mark.asyncio
async def test_add_message_to_conversation(temp_db):
    """Test adding a message to a conversation"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    conv_id = await db.create_conversation(title="Test")
    message_id = await db.add_message(
        conversation_id=conv_id, role="user", content="Hello, Sarah!"
    )

    assert message_id is not None
    assert isinstance(message_id, str)


@pytest.mark.asyncio
async def test_get_conversation_messages(temp_db):
    """Test retrieving all messages in a conversation"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    conv_id = await db.create_conversation(title="Test")
    await db.add_message(conv_id, "user", "Message 1")
    await db.add_message(conv_id, "assistant", "Response 1")
    await db.add_message(conv_id, "user", "Message 2")

    messages = await db.get_conversation_messages(conv_id)

    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Message 1"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


@pytest.mark.asyncio
async def test_add_message_with_tool_calls(temp_db):
    """Test adding a message with tool call metadata"""
    from database.db import Database
    import json

    db = Database(temp_db)
    await db.init_db()

    conv_id = await db.create_conversation(title="Test")
    tool_calls = [{"name": "save_journal", "args": {"content": "test"}}]

    message_id = await db.add_message(
        conversation_id=conv_id,
        role="assistant",
        content="I'll save that for you",
        tool_calls=tool_calls,
    )

    messages = await db.get_conversation_messages(conv_id)
    assert len(messages) == 1
    assert messages[0]["tool_calls"] is not None
    # Tool calls should be stored as JSON string
    stored_calls = json.loads(messages[0]["tool_calls"])
    assert stored_calls == tool_calls


@pytest.mark.asyncio
async def test_create_journal_entry(temp_db):
    """Test creating a journal entry"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    entry_id = await db.create_journal_entry(
        content="I had a great day today!", entry_type="autonomous"
    )

    assert entry_id is not None
    assert isinstance(entry_id, str)


@pytest.mark.asyncio
async def test_create_journal_entry_with_conversation_link(temp_db):
    """Test creating a journal entry linked to a conversation"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    conv_id = await db.create_conversation(title="Test")
    entry_id = await db.create_journal_entry(
        content="Important moment", entry_type="user_requested", conversation_id=conv_id
    )

    entry = await db.get_journal_entry(entry_id)
    assert entry["conversation_id"] == conv_id


@pytest.mark.asyncio
async def test_get_journal_entry(temp_db):
    """Test retrieving a specific journal entry"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    entry_id = await db.create_journal_entry(
        content="Test entry", entry_type="autonomous"
    )

    entry = await db.get_journal_entry(entry_id)

    assert entry is not None
    assert entry["id"] == entry_id
    assert entry["content"] == "Test entry"
    assert entry["entry_type"] == "autonomous"


@pytest.mark.asyncio
async def test_list_journal_entries(temp_db):
    """Test listing journal entries"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    await db.create_journal_entry("Entry 1", "autonomous")
    await db.create_journal_entry("Entry 2", "user_requested")
    await db.create_journal_entry("Entry 3", "autonomous")

    entries = await db.list_journal_entries()

    assert len(entries) == 3


@pytest.mark.asyncio
async def test_list_journal_entries_filtered_by_type(temp_db):
    """Test filtering journal entries by type"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    await db.create_journal_entry("Entry 1", "autonomous")
    await db.create_journal_entry("Entry 2", "user_requested")
    await db.create_journal_entry("Entry 3", "autonomous")

    entries = await db.list_journal_entries(entry_type="autonomous")

    assert len(entries) == 2
    assert all(e["entry_type"] == "autonomous" for e in entries)


@pytest.mark.asyncio
async def test_list_journal_entries_with_limit(temp_db):
    """Test limiting journal entries results"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    for i in range(10):
        await db.create_journal_entry(f"Entry {i}", "autonomous")

    entries = await db.list_journal_entries(limit=5)

    assert len(entries) == 5


@pytest.mark.asyncio
async def test_delete_journal_entry(temp_db):
    """Test deleting a journal entry"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    entry_id = await db.create_journal_entry("To delete", "autonomous")
    success = await db.delete_journal_entry(entry_id)

    assert success is True

    entry = await db.get_journal_entry(entry_id)
    assert entry is None


@pytest.mark.asyncio
async def test_set_setting(temp_db):
    """Test setting a configuration value"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    await db.set_setting("llm_model", "llama3.2:latest")
    value = await db.get_setting("llm_model")

    assert value == "llama3.2:latest"


@pytest.mark.asyncio
async def test_get_all_settings(temp_db):
    """Test retrieving all settings"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    await db.set_setting("setting1", "value1")
    await db.set_setting("setting2", "value2")

    settings = await db.get_all_settings()

    assert settings["setting1"] == "value1"
    assert settings["setting2"] == "value2"


@pytest.mark.asyncio
async def test_settings_encryption_for_api_keys(temp_db):
    """Test that API keys are encrypted when stored"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    api_key = "sk-test-1234567890abcdef"
    await db.set_setting("api_key", api_key, encrypt=True)

    # Check that raw value in database is NOT the plaintext key
    async with aiosqlite.connect(temp_db) as conn:
        cursor = await conn.execute(
            "SELECT value FROM settings WHERE key = ?", ("api_key",)
        )
        row = await cursor.fetchone()
        encrypted_value = row[0]

    assert encrypted_value != api_key

    # But when retrieved through the API, it should be decrypted
    decrypted = await db.get_setting("api_key", decrypt=True)
    assert decrypted == api_key


@pytest.mark.asyncio
async def test_cascade_delete_messages_with_conversation(temp_db):
    """Test that deleting a conversation cascades to messages"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    conv_id = await db.create_conversation(title="Test")
    await db.add_message(conv_id, "user", "Message 1")
    await db.add_message(conv_id, "assistant", "Response 1")

    # Delete conversation
    await db.delete_conversation(conv_id)

    # Messages should be deleted too
    messages = await db.get_conversation_messages(conv_id)
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_journal_entry_conversation_set_null_on_delete(temp_db):
    """Test that deleting a conversation sets journal entry conversation_id to NULL"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    conv_id = await db.create_conversation(title="Test")
    entry_id = await db.create_journal_entry(
        content="Important", entry_type="autonomous", conversation_id=conv_id
    )

    # Delete conversation
    await db.delete_conversation(conv_id)

    # Journal entry should remain but conversation_id should be NULL
    entry = await db.get_journal_entry(entry_id)
    assert entry is not None
    assert entry["conversation_id"] is None


@pytest.mark.asyncio
async def test_default_settings_initialized(temp_db):
    """Test that default settings are created on first run"""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    settings = await db.get_all_settings()

    # Should have default LLM settings
    assert "llm_endpoint" in settings
    assert "llm_model" in settings
    assert "api_key" in settings


@pytest.mark.asyncio
async def test_create_entity(temp_db):
    """Test creating an entity."""
    from database.db import Database
    import json

    db = Database(temp_db)
    await db.init_db()

    entity_id = await db.create_entity(
        entity_type="person",
        name="John Doe",
        description="Designer from tech conference",
        metadata={"relationship": "colleague"},
    )

    assert entity_id is not None

    # Retrieve entity
    entity = await db.get_entity(entity_id)
    assert entity["name"] == "John Doe"
    assert entity["type"] == "person"
    assert entity["description"] == "Designer from tech conference"
    assert json.loads(entity["metadata"])["relationship"] == "colleague"


@pytest.mark.asyncio
async def test_update_entity(temp_db):
    """Test updating an entity."""
    from database.db import Database
    import json

    db = Database(temp_db)
    await db.init_db()

    entity_id = await db.create_entity(entity_type="person", name="John Doe")

    # Update entity
    await db.update_entity(
        entity_id,
        description="Updated description",
        metadata={"relationship": "friend", "phone": "555-1234"},
    )

    # Verify update
    entity = await db.get_entity(entity_id)
    assert entity["description"] == "Updated description"
    metadata = json.loads(entity["metadata"])
    assert metadata["relationship"] == "friend"
    assert metadata["phone"] == "555-1234"


@pytest.mark.asyncio
async def test_search_entities(temp_db):
    """Test searching entities."""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    # Create test entities
    await db.create_entity("person", "John Doe", "Designer from conference")
    await db.create_entity("person", "Jane Smith", "Product manager")
    await db.create_entity("place", "Coffee Shop", "Downtown cafe")

    # Search by name
    results = await db.search_entities(query="John", entity_type=None, limit=10)
    assert len(results) == 1
    assert results[0]["name"] == "John Doe"

    # Search by type
    results = await db.search_entities(query=None, entity_type="person", limit=10)
    assert len(results) == 2

    # Search by description
    results = await db.search_entities(query="cafe", entity_type=None, limit=10)
    assert len(results) == 1
    assert results[0]["name"] == "Coffee Shop"


@pytest.mark.asyncio
async def test_create_event(temp_db):
    """Test creating an event."""
    from database.db import Database
    import json

    db = Database(temp_db)
    await db.init_db()

    # Create participants
    person_id = await db.create_entity("person", "John Doe")
    place_id = await db.create_entity("place", "Coffee Shop")

    event_id = await db.create_event(
        name="Coffee Meeting",
        description="Discussed design project",
        event_date="2025-12-12T10:00:00",
        participants=[person_id],
        location=place_id,
    )

    assert event_id is not None

    # Retrieve event
    event = await db.get_event(event_id)
    assert event["name"] == "Coffee Meeting"
    assert event["description"] == "Discussed design project"
    assert json.loads(event["participants"]) == [person_id]
    assert event["location"] == place_id


@pytest.mark.asyncio
async def test_search_events(temp_db):
    """Test searching events."""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    person_id = await db.create_entity("person", "John Doe")

    # Create events
    event1_id = await db.create_event(
        name="Coffee Meeting", description="Morning coffee", participants=[person_id]
    )
    event2_id = await db.create_event(
        name="Tech Conference", description="Annual tech event"
    )

    # Search by name
    results = await db.search_events(query="coffee", limit=10)
    assert len(results) == 1
    assert results[0]["name"] == "Coffee Meeting"

    # Search by participant
    results = await db.search_events(participant_id=person_id, limit=10)
    assert len(results) == 1
    assert results[0]["id"] == event1_id


@pytest.mark.asyncio
async def test_create_journal(temp_db):
    """Test creating a journal entry."""
    from database.db import Database
    import json

    db = Database(temp_db)
    await db.init_db()

    # Create related entities and event
    person_id = await db.create_entity("person", "John Doe")
    event_id = await db.create_event("Coffee Meeting")

    journal_id = await db.create_journal(
        content="Had a great discussion about design patterns",
        related_entities=[person_id],
        related_event_id=event_id,
    )

    assert journal_id is not None

    # Retrieve journal
    journal = await db.get_journal(journal_id)
    assert journal["content"] == "Had a great discussion about design patterns"
    assert json.loads(journal["related_entities"]) == [person_id]
    assert journal["related_event_id"] == event_id


@pytest.mark.asyncio
async def test_search_journals(temp_db):
    """Test searching journals."""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    person_id = await db.create_entity("person", "John Doe")

    # Create journals
    await db.create_journal(
        content="Met John at the coffee shop", related_entities=[person_id]
    )
    await db.create_journal(content="Worked on the project all day")

    # Search by content
    results = await db.search_journals(query="coffee", limit=10)
    assert len(results) == 1
    assert "coffee shop" in results[0]["content"]

    # Search by entity
    results = await db.search_journals(entity_id=person_id, limit=10)
    assert len(results) == 1
    assert "Met John" in results[0]["content"]


@pytest.mark.asyncio
async def test_create_rating(temp_db):
    """Test creating a rating."""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    # Create entity to rate
    entity_id = await db.create_entity("place", "Italian Restaurant")

    rating_id = await db.create_rating(
        target_type="entity",
        target_id=entity_id,
        category="meal",
        score=5,
        notes="Amazing pasta!",
    )

    assert rating_id is not None

    # Retrieve rating
    rating = await db.get_rating(rating_id)
    assert rating["target_type"] == "entity"
    assert rating["target_id"] == entity_id
    assert rating["category"] == "meal"
    assert rating["score"] == 5
    assert rating["notes"] == "Amazing pasta!"


@pytest.mark.asyncio
async def test_get_ratings_for_target(temp_db):
    """Test getting ratings for a specific target."""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    entity_id = await db.create_entity("place", "Restaurant")

    # Create multiple ratings
    await db.create_rating("entity", entity_id, "meal", 5, "Great dinner")
    await db.create_rating("entity", entity_id, "meal", 4, "Good lunch")

    # Get ratings
    results = await db.get_ratings_by_target("entity", entity_id, limit=10)
    assert len(results["ratings"]) == 2
    assert results["statistics"]["average"] == 4.5
    assert results["statistics"]["count"] == 2


@pytest.mark.asyncio
async def test_get_ratings_by_category(temp_db):
    """Test getting ratings by category."""
    from database.db import Database

    db = Database(temp_db)
    await db.init_db()

    entity1_id = await db.create_entity("place", "Restaurant")
    entity2_id = await db.create_entity("thing", "Movie")

    await db.create_rating("entity", entity1_id, "meal", 5)
    await db.create_rating("entity", entity2_id, "entertainment", 4)

    # Get meal ratings
    results = await db.get_ratings_by_category("meal", limit=10)
    assert len(results["ratings"]) == 1
    assert results["ratings"][0]["category"] == "meal"
