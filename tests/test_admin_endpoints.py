"""
Tests for admin endpoints including plugin reload.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import shutil


def test_reload_plugins_endpoint(tmpdir):
    """Test that the reload plugins endpoint works."""
    # This is more of an integration test
    # We'll just verify the endpoint exists and returns expected structure
    from main import app, plugin_loader
    
    # Set plugin_loader to use temp directory
    plugin_loader.plugin_dir = Path(tmpdir)
    plugin_loader.load_plugins()
    
    client = TestClient(app)
    response = client.post("/api/admin/reload-plugins")
    
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert data["success"] is True
    assert "tools_count" in data
    assert "plugins_loaded" in data
    assert "plugins_failed" in data
    assert "plugins" in data
    assert isinstance(data["plugins"], list)


def test_get_plugins_endpoint():
    """Test that the get plugins endpoint works."""
    from main import app
    
    client = TestClient(app)
    response = client.get("/api/admin/plugins")
    
    assert response.status_code == 200
    data = response.json()
    assert "tools_count" in data
    assert "plugins_loaded" in data
    assert "plugins_failed" in data
    assert "plugins" in data
    assert "tool_names" in data
    assert isinstance(data["plugins"], list)
    assert isinstance(data["tool_names"], list)
