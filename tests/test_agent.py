"""
Tests for KrellAgent - Strands agent integration

Following TDD: These tests are written BEFORE implementing the KrellAgent class.
They define the expected behavior of the agent integration.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from database.db import Database
from core.agent import KrellAgent


@pytest_asyncio.fixture
async def temp_db():
    """Create a temporary database for testing"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name

    db = Database(db_path)
    await db.init_db()

    yield db

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)
    key_path = Path(db_path).parent / ".encryption_key"
    if os.path.exists(key_path):
        os.unlink(key_path)


@pytest_asyncio.fixture
async def db_with_settings(temp_db):
    """Database with LLM settings configured"""
    await temp_db.set_setting("llm_endpoint", "http://localhost:11434")
    await temp_db.set_setting("llm_model", "llama3.2:latest")
    await temp_db.set_setting("api_key", "test-api-key")
    return temp_db


@pytest_asyncio.fixture
async def db_with_conversation(db_with_settings):
    """Database with a conversation and messages"""
    db = db_with_settings

    # Create conversation
    conv_id = await db.create_conversation("Test Conversation")

    # Add some messages
    await db.add_message(conv_id, "user", "Hello")
    await db.add_message(conv_id, "assistant", "Hi! How can I help you today?")
    await db.add_message(conv_id, "user", "Tell me about AI")
    await db.add_message(conv_id, "assistant", "AI is fascinating! It involves...")

    return db, conv_id


@pytest.mark.asyncio
class TestKrellAgentInitialization:
    """Test KrellAgent initialization from database settings"""

    async def test_agent_initializes_with_db_settings(self, db_with_settings):
        """Agent should initialize using settings from database"""
        from core.agent import KrellAgent

        agent = await KrellAgent.create(db_with_settings)

        # Agent should be created successfully
        assert agent is not None
        assert agent.db == db_with_settings

    async def test_agent_loads_llm_config_from_db(self, db_with_settings):
        """Agent should load LLM endpoint and model from database"""
        from core.agent import KrellAgent

        agent = await KrellAgent.create(db_with_settings)

        # Should have loaded settings
        assert agent.llm_endpoint == "http://localhost:11434"
        assert agent.llm_model == "llama3.2:latest"

    async def test_agent_uses_default_context_limit(self, db_with_settings):
        """Agent should use default context limit of 20 messages"""
        from core.agent import KrellAgent

        agent = await KrellAgent.create(db_with_settings)

        assert agent.context_limit == 20

    async def test_agent_accepts_custom_context_limit(self, db_with_settings):
        """Agent should accept custom context limit"""
        from core.agent import KrellAgent

        agent = await KrellAgent.create(db_with_settings, context_limit=10)

        assert agent.context_limit == 10

    async def test_agent_has_sarah_system_prompt(self, db_with_settings):
        """Agent should have Sarah's system prompt configured"""
        from core.agent import KrellAgent

        agent = await KrellAgent.create(db_with_settings)

        # System prompt should mention Sarah and journal entries
        assert "Krell" in agent.system_prompt
        assert "journal" in agent.system_prompt.lower()


@pytest.mark.asyncio
class TestKrellAgentConversationHistory:
    """Test loading conversation history into agent context"""

    async def test_agent_loads_conversation_history(self, db_with_conversation):
        """Agent should load conversation messages into context"""
        from core.agent import KrellAgent

        db, conv_id = db_with_conversation
        agent = await KrellAgent.create(db)

        # Load conversation
        messages = await agent.load_conversation_history(conv_id)

        # Should have 4 messages
        assert len(messages) == 4
        assert messages[0]["role"] == "user"
        # Content is now in ContentBlock format: [{"text": "..."}]
        assert messages[0]["content"][0]["text"] == "Hello"
        assert messages[3]["role"] == "assistant"

    async def test_agent_respects_context_limit(self, db_with_settings):
        """Agent should limit loaded messages to context_limit"""
        from core.agent import KrellAgent

        db = db_with_settings

        # Create conversation with many messages
        conv_id = await db.create_conversation("Long Conversation")
        for i in range(30):
            await db.add_message(conv_id, "user", f"Message {i}")
            await db.add_message(conv_id, "assistant", f"Response {i}")

        # Create agent with context limit of 20
        agent = await KrellAgent.create(db, context_limit=20)

        # Load conversation
        messages = await agent.load_conversation_history(conv_id)

        # Should only have last 20 messages
        assert len(messages) == 20
        # Should be the most recent messages (first message should be from the last 20)
        first_msg_text = messages[0]["content"][0]["text"]
        assert "Message 20" in first_msg_text or "Response 20" in first_msg_text

    async def test_agent_handles_empty_conversation(self, db_with_settings):
        """Agent should handle conversation with no messages"""
        from core.agent import KrellAgent

        db = db_with_settings
        conv_id = await db.create_conversation("Empty Conversation")

        agent = await KrellAgent.create(db)
        messages = await agent.load_conversation_history(conv_id)

        assert len(messages) == 0


@pytest.mark.asyncio
class TestKrellAgentChatResponse:
    """Test agent generating responses (mocked LLM)"""

    async def test_agent_generates_response_without_tools(self, db_with_conversation):
        """Agent should generate response using Strands agent"""
        from core.agent import KrellAgent

        db, conv_id = db_with_conversation
        agent = await KrellAgent.create(db)

        # Mock the underlying Strands agent to avoid actual LLM calls
        with patch.object(agent, "_strands_agent") as mock_agent:
            mock_agent.return_value = "This is a test response"

            # Generate response
            response = await agent.chat(conv_id, "What is AI?")

            # Should return response dict
            assert "response" in response
            assert "tool_calls" in response
            assert response["response"] == "This is a test response"

    async def test_agent_returns_tool_call_metadata(self, db_with_settings):
        """Agent should return tool call metadata when tools are used"""
        from core.agent import KrellAgent

        agent = await KrellAgent.create(db_with_settings)
        conv_id = await db_with_settings.create_conversation("Tool Test")

        # Mock agent with tool calls
        with patch.object(agent, "_strands_agent") as mock_agent:
            # Simulate agent calling a tool
            mock_agent.return_value = MagicMock(
                response="I've saved that to your journal",
                tool_calls=[
                    {
                        "tool": "save_journal_entry",
                        "args": {"content": "Test entry", "entry_type": "autonomous"},
                    }
                ],
            )

            response = await agent.chat(conv_id, "I'm feeling happy today")

            # Should include tool call metadata
            assert len(response["tool_calls"]) == 1
            assert response["tool_calls"][0]["tool"] == "save_journal_entry"

    async def test_agent_saves_messages_to_db(self, db_with_settings):
        """Agent should save user message and response to database"""
        from core.agent import KrellAgent

        db = db_with_settings
        conv_id = await db.create_conversation("Save Test")

        agent = await KrellAgent.create(db)

        with patch.object(agent, "_strands_agent") as mock_agent:
            mock_agent.return_value = "Test response"

            await agent.chat(conv_id, "Test message")

        # Check messages were saved
        messages = await db.get_conversation_messages(conv_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Test message"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Test response"

    async def test_agent_creates_new_conversation_if_needed(self, db_with_settings):
        """Agent should create new conversation if conversation_id is None"""
        from core.agent import KrellAgent

        agent = await KrellAgent.create(db_with_settings)

        with patch.object(agent, "_strands_agent") as mock_agent:
            mock_agent.return_value = "Hello!"

            response = await agent.chat(None, "Hi")

        # Should return a conversation_id
        assert "conversation_id" in response
        assert response["conversation_id"] is not None

        # Conversation should exist in database
        conv = await db_with_settings.get_conversation(response["conversation_id"])
        assert conv is not None


@pytest.mark.asyncio
class TestKrellAgentConfiguration:
    """Test agent configuration from settings"""

    async def test_agent_uses_custom_endpoint(self, temp_db):
        """Agent should use custom LLM endpoint from settings"""
        from core.agent import KrellAgent

        await temp_db.set_setting("llm_endpoint", "http://custom-llm:8080")
        await temp_db.set_setting("llm_model", "custom-model")

        agent = await KrellAgent.create(temp_db)

        assert agent.llm_endpoint == "http://custom-llm:8080"
        assert agent.llm_model == "custom-model"

    async def test_agent_handles_missing_settings_gracefully(self, temp_db):
        """Agent should use defaults if settings are missing"""
        from core.agent import KrellAgent

        # Don't set any custom settings, use defaults from DB init
        agent = await KrellAgent.create(temp_db)

        # Should still initialize with defaults
        assert agent is not None
        assert agent.llm_endpoint == "http://localhost:11434"
        assert agent.llm_model == "llama3.2:latest"


@pytest.mark.asyncio
async def test_agent_system_prompt_is_scribe_focused():
    """Test that agent uses the new scribe-focused system prompt."""
    db = Database(":memory:")

    agent = KrellAgent(
        db=db,
        llm_endpoint="https://api.openai.com",
        llm_model="gpt-4o-mini",
        openai_api_key="test-key",
    )

    # Verify system prompt contains scribe-related language
    assert "information assistant" in agent.system_prompt.lower()
    assert "scribe" in agent.system_prompt.lower()
    assert (
        "capture" in agent.system_prompt.lower()
        or "record" in agent.system_prompt.lower()
    )

    # Should NOT contain old companion language
    assert "confidant" not in agent.system_prompt.lower()
    assert "warm" not in agent.system_prompt.lower()
