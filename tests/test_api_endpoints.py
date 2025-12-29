"""
Tests for new API endpoints (Task 7).

Following TDD: Write test first, watch it fail, then implement.
These are integration tests using TestClient.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from main import app

    return TestClient(app)


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
