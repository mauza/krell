"""
Tests for admin endpoints including plugin reload.
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile
import os
import shutil


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)
    # Also clean up encryption key
    key_path = os.path.dirname(db_path) + "/.encryption_key"
    if os.path.exists(key_path):
        os.unlink(key_path)


@pytest.fixture
def authenticated_client(temp_db):
    """Create an isolated test client that is already authenticated."""
    import sys

    # Store original modules
    original_modules = {}
    modules_to_reload = ["main", "database.db", "config"]
    for mod in modules_to_reload:
        if mod in sys.modules:
            original_modules[mod] = sys.modules[mod]

    # Set environment for test db
    os.environ["KRELL_TEST_DB"] = temp_db

    try:
        # Clear cached modules to force reimport
        for mod in list(sys.modules.keys()):
            if (
                mod.startswith("main")
                or mod.startswith("database")
                or mod.startswith("config")
            ):
                if mod in sys.modules:
                    del sys.modules[mod]

        # Import with test config
        from config import Config

        Config._instance = None  # Reset singleton if any

        from database.db import Database, ConversationDB
        from main import app, db

        # Override db path
        db.db_path = temp_db

        # Initialize database
        import asyncio

        database = Database(temp_db)
        asyncio.get_event_loop().run_until_complete(database.init_db())

        client = TestClient(app)

        # Set up authentication: create password and login
        client.post(
            "/dashboard/setup",
            data={
                "password": "testpassword123",
                "confirm_password": "testpassword123",
            },
        )
        client.post("/dashboard/login", data={"password": "testpassword123"})

        yield client
    finally:
        # Restore original modules
        for mod, module in original_modules.items():
            sys.modules[mod] = module
        if "KRELL_TEST_DB" in os.environ:
            del os.environ["KRELL_TEST_DB"]


def test_reload_plugins_endpoint(authenticated_client, tmpdir):
    """Test that the reload plugins endpoint works."""
    from main import plugin_loader

    # Set plugin_loader to use temp directory
    plugin_loader.plugin_dir = Path(tmpdir)
    plugin_loader.load_plugins()

    response = authenticated_client.post("/api/admin/reload-plugins")

    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert data["success"] is True
    assert "tools_count" in data
    assert "plugins_loaded" in data
    assert "plugins_failed" in data
    assert "plugins" in data
    assert isinstance(data["plugins"], list)


def test_get_plugins_endpoint(authenticated_client):
    """Test that the get plugins endpoint works."""
    response = authenticated_client.get("/api/admin/plugins")

    assert response.status_code == 200
    data = response.json()
    assert "tools_count" in data
    assert "plugins_loaded" in data
    assert "plugins_failed" in data
    assert "plugins" in data
    assert "tool_names" in data
    assert isinstance(data["plugins"], list)
    assert isinstance(data["tool_names"], list)
