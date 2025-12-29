"""
Tests for new API endpoints (Task 7).

Following TDD: Write test first, watch it fail, then implement.
These are integration tests using TestClient.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from main import app

    return TestClient(app)


@pytest.fixture
def mock_agent():
    """Create a mock KrellAgent for testing."""
    mock = Mock()
    mock.chat = AsyncMock(
        return_value={
            "response": "This is a test response from Sarah.",
            "conversation_id": "test-conv-id",
            "tool_calls": [],
        }
    )
    return mock


# ============================================================================
# POST /api/chat Tests
# ============================================================================


def test_chat_creates_new_conversation_when_no_id_provided(client, mock_agent):
    """POST /api/chat without conversation_id should create new conversation."""
    with patch("api.routes.get_krell_agent", return_value=mock_agent):
        response = client.post("/api/chat", json={"message": "Hello, Sarah!"})

    assert response.status_code == 200
    data = response.json()

    assert "response" in data
    assert "conversation_id" in data
    assert "tool_calls" in data
    assert data["response"] == "This is a test response from Sarah."
    assert isinstance(data["conversation_id"], str)
    assert len(data["conversation_id"]) > 0


def test_chat_continues_existing_conversation(client, mock_agent):
    """POST /api/chat with conversation_id should continue conversation."""
    test_conv_id = "existing-conv-id"

    with patch("api.routes.get_krell_agent", return_value=mock_agent):
        mock_agent.chat.return_value = {
            "response": "Continuing our conversation!",
            "conversation_id": test_conv_id,
            "tool_calls": [],
        }

        response = client.post(
            "/api/chat",
            json={
                "conversation_id": test_conv_id,
                "message": "Remember what we discussed?",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == test_conv_id
    assert data["response"] == "Continuing our conversation!"


# ============================================================================
# GET /api/conversations Tests
# ============================================================================


def test_list_conversations_returns_list(client):
    """GET /api/conversations should return a list."""
    response = client.get("/api/conversations")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


# ============================================================================
# GET /api/conversations/{id} Tests
# ============================================================================


def test_get_conversation_404_when_not_found(client):
    """GET /api/conversations/{id} should return 404 when not found."""
    response = client.get("/api/conversations/nonexistent-id")

    assert response.status_code == 404


# ============================================================================
# DELETE /api/conversations/{id} Tests
# ============================================================================


def test_delete_conversation_404_when_not_found(client):
    """DELETE /api/conversations/{id} should return 404 when not found."""
    response = client.delete("/api/conversations/nonexistent-id")

    assert response.status_code == 404


# ============================================================================
# PATCH /api/conversations/{id} Tests
# ============================================================================


def test_update_conversation_title_404_when_not_found(client):
    """PATCH /api/conversations/{id} should return 404 when not found."""
    response = client.patch(
        "/api/conversations/nonexistent-id", json={"title": "New Title"}
    )

    assert response.status_code == 404


# ============================================================================
# GET /api/settings Tests
# ============================================================================


def test_get_settings_returns_settings_dict(client):
    """GET /api/settings should return settings dict."""
    response = client.get("/api/settings")

    assert response.status_code == 200
    data = response.json()
    assert "settings" in data
    assert isinstance(data["settings"], dict)


# ============================================================================
# POST /api/settings Tests
# ============================================================================


def test_update_settings_accepts_settings_dict(client):
    """POST /api/settings should accept settings dict."""
    response = client.post(
        "/api/settings", json={"settings": {"llm_model": "test-model"}}
    )

    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert data["success"] is True


# ============================================================================
# GET /api/config Tests
# ============================================================================


def test_config_shows_loaded_plugins(client):
    """GET /api/config should show loaded plugins."""
    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert "agentic_enabled" in data
    assert "loaded_plugins" in data
    assert isinstance(data["loaded_plugins"], list)
