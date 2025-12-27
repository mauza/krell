"""
Tests for conversation_tool.py plugin.

Following TDD - tests written first, watched fail, then implementation added.
"""

import pytest
import pytest_asyncio
import tempfile
import shutil
from pathlib import Path
from database.db import Database
from core.plugin_loader import PluginLoader


class TestConversationToolPlugin:
    """Tests for conversation_tool plugin loading and structure."""

    def test_conversation_tool_plugin_loads(self):
        """Test that conversation_tool.py plugin loads successfully."""
        loader = PluginLoader(plugin_dir="plugins")
        loader.load_plugins()

        # Find conversation_tool in loaded plugins
        metadata = loader.get_plugin_metadata()
        conv_plugin = None
        for plugin in metadata:
            if plugin["filename"] == "conversation_tool.py":
                conv_plugin = plugin
                break

        assert conv_plugin is not None, "conversation_tool.py should be loaded"
        assert conv_plugin["status"] == "loaded"
        assert "search_past_conversations" in conv_plugin["functions"]

    def test_conversation_tool_is_callable(self):
        """Test that conversation tool is properly decorated and callable."""
        loader = PluginLoader(plugin_dir="plugins")
        loader.load_plugins()

        tools = loader.get_tools()
        tool_names = [tool.tool_name for tool in tools]

        assert "search_past_conversations" in tool_names


class TestConversationToolFunctionality:
    """Tests for conversation tool business logic with test database."""

    @pytest_asyncio.fixture
    async def test_db(self):
        """Create a temporary test database with some conversations."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test.db"
        database = Database(str(db_path))
        await database.init_db()

        # Create some test conversations
        conv1_id = await database.create_conversation("Discussing AI")
        await database.add_message(
            conv1_id, "user", "What do you think about artificial intelligence?"
        )
        await database.add_message(
            conv1_id, "assistant", "AI is fascinating and transforming many industries."
        )

        conv2_id = await database.create_conversation("Planning vacation")
        await database.add_message(conv2_id, "user", "I want to plan a trip to Japan")
        await database.add_message(
            conv2_id, "assistant", "Japan is a wonderful destination!"
        )

        conv3_id = await database.create_conversation("Cooking recipes")
        await database.add_message(conv3_id, "user", "How do I make pasta carbonara?")
        await database.add_message(
            conv3_id, "assistant", "Carbonara is made with eggs, cheese, and guanciale."
        )

        yield database
        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_search_past_conversations_finds_matches(self, test_db):
        """Test that search_past_conversations finds relevant conversations."""
        from plugins import conversation_tool

        # Search for "AI"
        result = await conversation_tool.search_past_conversations_async(
            test_db, query="AI"
        )

        # Verify result structure
        assert "results" in result
        assert len(result["results"]) > 0

        # Verify AI conversation is in results
        found_ai = False
        for conv in result["results"]:
            if "AI" in conv["title"] or "artificial intelligence" in str(conv).lower():
                found_ai = True
                break
        assert found_ai, "Should find the AI conversation"

    @pytest.mark.asyncio
    async def test_search_past_conversations_respects_limit(self, test_db):
        """Test that search respects the limit parameter."""
        from plugins import conversation_tool

        # Create many more conversations
        for i in range(10):
            conv_id = await test_db.create_conversation(f"Test conversation {i}")
            await test_db.add_message(conv_id, "user", f"Message {i}")

        # Search with limit
        result = await conversation_tool.search_past_conversations_async(
            test_db, query="conversation", limit=3
        )

        # Verify limit was respected
        assert len(result["results"]) <= 3

    @pytest.mark.asyncio
    async def test_search_past_conversations_returns_empty_for_no_matches(
        self, test_db
    ):
        """Test that search returns empty results for no matches."""
        from plugins import conversation_tool

        # Search for something that doesn't exist
        result = await conversation_tool.search_past_conversations_async(
            test_db, query="xyznonexistent"
        )

        # Verify empty results
        assert "results" in result
        assert len(result["results"]) == 0

    @pytest.mark.asyncio
    async def test_search_past_conversations_searches_messages_too(self, test_db):
        """Test that search looks in message content, not just titles."""
        from plugins import conversation_tool

        # Search for "carbonara" which is only in messages
        result = await conversation_tool.search_past_conversations_async(
            test_db, query="carbonara"
        )

        # Verify result found
        assert len(result["results"]) > 0

        # Verify it's the cooking conversation
        found_cooking = False
        for conv in result["results"]:
            if "Cooking" in conv["title"] or "carbonara" in str(conv).lower():
                found_cooking = True
                break
        assert found_cooking, "Should find conversation with carbonara in messages"

    @pytest.mark.asyncio
    async def test_search_past_conversations_includes_relevant_snippets(self, test_db):
        """Test that search results include conversation snippets."""
        from plugins import conversation_tool

        # Search for "Japan"
        result = await conversation_tool.search_past_conversations_async(
            test_db, query="Japan"
        )

        # Verify results have snippets
        assert len(result["results"]) > 0

        # Each result should have title and some content
        for conv in result["results"]:
            assert "title" in conv
            # Should have either messages or content field
            assert "messages" in conv or "content" in conv or "snippet" in conv
