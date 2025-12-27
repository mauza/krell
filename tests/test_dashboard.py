"""
Tests for dashboard UI (Task 8).

Following TDD: Write test first, watch it fail, then implement.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from main import app

    return TestClient(app)


# ============================================================================
# Dashboard Page Tests
# ============================================================================


def test_dashboard_returns_html(client):
    """
    RED TEST: GET /dashboard should return HTML page.

    Expected behavior:
    - Returns 200 status
    - Content-Type is text/html
    - Contains dashboard title
    """
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Krell Dashboard" in response.text or "Dashboard" in response.text


# ============================================================================
# Dashboard API - Status Endpoint Tests
# ============================================================================


def test_dashboard_status_returns_system_info(client):
    """
    RED TEST: GET /dashboard/api/status should return system status.

    Expected behavior:
    - Returns JSON with uptime, conversation count, journal entry count
    """
    response = client.get("/dashboard/api/status")

    assert response.status_code == 200
    data = response.json()

    assert "uptime" in data
    assert "total_conversations" in data
    assert "total_journal_entries" in data
    assert isinstance(data["total_conversations"], int)
    assert isinstance(data["total_journal_entries"], int)


# ============================================================================
# Dashboard API - Settings Tests
# ============================================================================


def test_dashboard_get_settings_returns_config(client):
    """
    RED TEST: GET /dashboard/api/settings should return LLM configuration.

    Expected behavior:
    - Returns current LLM settings
    - API key is masked
    """
    response = client.get("/dashboard/api/settings")

    assert response.status_code == 200
    data = response.json()

    assert "llm_endpoint" in data
    assert "llm_model" in data
    assert "api_key" in data

    # API key should be masked if set
    if data["api_key"]:
        assert "•" in data["api_key"] or data["api_key"] == ""


def test_dashboard_update_settings_saves_to_db(client):
    """
    RED TEST: POST /dashboard/api/settings should update settings.

    Expected behavior:
    - Accepts settings dict
    - Saves to database
    - Returns success response
    """
    response = client.post(
        "/dashboard/api/settings",
        json={
            "llm_endpoint": "http://localhost:11434",
            "llm_model": "llama3.2:latest",
            "api_key": "test-key-123",
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "message" in data


# ============================================================================
# Dashboard API - Test Connection Tests
# ============================================================================


def test_dashboard_test_connection_checks_llm(client):
    """
    RED TEST: POST /dashboard/api/test-connection should test LLM connection.

    Expected behavior:
    - Tests connection to LLM endpoint
    - Returns status and latency
    """
    response = client.post(
        "/dashboard/api/test-connection",
        json={"endpoint": "http://localhost:11434", "model": "llama3.2:latest"},
    )

    assert response.status_code == 200
    data = response.json()

    assert "success" in data
    assert "latency_ms" in data or "error" in data

    if data["success"]:
        assert isinstance(data["latency_ms"], (int, float))


def test_dashboard_test_connection_detects_openai_compatible_endpoints(client):
    """
    RED TEST: POST /dashboard/api/test-connection should detect OpenAI-compatible endpoints.

    Expected behavior:
    - Detects OpenAI-compatible endpoints (api.openai.com, openrouter.ai, etc.)
    - Uses appropriate test endpoint (/v1/models instead of /api/generate)
    - Returns success for valid OpenAI-compatible endpoints
    """
    # Test with OpenAI endpoint format
    response = client.post(
        "/dashboard/api/test-connection",
        json={"endpoint": "https://api.openai.com", "model": "gpt-3.5-turbo"},
    )

    assert response.status_code == 200
    data = response.json()

    # Should attempt connection and return result
    assert "success" in data
    assert "error" in data or "latency_ms" in data


def test_dashboard_test_connection_with_provider_parameter(client):
    """
    RED TEST: POST /dashboard/api/test-connection should accept explicit provider parameter.

    Expected behavior:
    - Accepts optional 'provider' parameter ('ollama' or 'openai')
    - Uses specified provider's test endpoint
    - Falls back to auto-detection if provider not specified
    """
    # Test with explicit Ollama provider
    response = client.post(
        "/dashboard/api/test-connection",
        json={
            "endpoint": "http://localhost:11434",
            "model": "llama3.2:latest",
            "provider": "ollama",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "success" in data

    # Test with explicit OpenAI provider
    response = client.post(
        "/dashboard/api/test-connection",
        json={
            "endpoint": "https://api.openai.com",
            "model": "gpt-3.5-turbo",
            "provider": "openai",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "success" in data


# ============================================================================
# Dashboard API - Plugins Tests
# ============================================================================


def test_dashboard_get_plugins_returns_loaded_plugins(client):
    """
    RED TEST: GET /dashboard/api/plugins should return loaded plugins info.

    Expected behavior:
    - Returns list of plugins with metadata
    - Shows plugin status, functions, load time
    """
    response = client.get("/dashboard/api/plugins")

    assert response.status_code == 200
    data = response.json()

    assert "plugins" in data
    assert isinstance(data["plugins"], list)

    # Check structure of plugin metadata
    if len(data["plugins"]) > 0:
        plugin = data["plugins"][0]
        assert "filename" in plugin
        assert "status" in plugin


def test_dashboard_reload_plugins_triggers_reload(client):
    """
    RED TEST: POST /dashboard/api/plugins/reload should reload plugins.

    Expected behavior:
    - Triggers plugin reload
    - Returns success and updated plugin count
    """
    response = client.post("/dashboard/api/plugins/reload")

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert "plugins_loaded" in data
    assert "tools_count" in data


# ============================================================================
# Dashboard API - Recent Activity Tests
# ============================================================================


def test_dashboard_get_recent_conversations(client):
    """
    RED TEST: GET /dashboard/api/recent/conversations should return recent conversations.

    Expected behavior:
    - Returns last 10 conversations
    - Each has id, title, timestamps
    """
    response = client.get("/dashboard/api/recent/conversations")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) <= 10

    # Check structure if any exist
    if len(data) > 0:
        conv = data[0]
        assert "id" in conv
        assert "title" in conv


def test_dashboard_get_recent_journal_entries(client):
    """
    RED TEST: GET /dashboard/api/recent/journal should return recent journal entries.

    Expected behavior:
    - Returns last 10 journal entries
    - Each has id, content, entry_type
    """
    response = client.get("/dashboard/api/recent/journal")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) <= 10

    # Check structure if any exist
    if len(data) > 0:
        entry = data[0]
        assert "id" in entry
        assert "content" in entry
        assert "entry_type" in entry
