"""Tests for admin authentication routes."""

import pytest
import tempfile
import os
from fastapi.testclient import TestClient


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
def isolated_client(temp_db):
    """Create a fully isolated test client for auth tests."""
    import sys
    import importlib

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

        yield TestClient(app)
    finally:
        # Restore original modules
        for mod, module in original_modules.items():
            sys.modules[mod] = module
        if "KRELL_TEST_DB" in os.environ:
            del os.environ["KRELL_TEST_DB"]


class TestSetupFlow:
    """Tests for initial password setup."""

    def test_dashboard_redirects_to_setup_when_no_password(self, isolated_client):
        """GET /dashboard should redirect to /dashboard/setup if no password set."""
        response = isolated_client.get("/dashboard", follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard/setup"

    def test_setup_page_renders(self, isolated_client):
        """GET /dashboard/setup should render setup form."""
        response = isolated_client.get("/dashboard/setup")

        assert response.status_code == 200
        assert b"Set Admin Password" in response.content

    def test_setup_post_passwords_must_match(self, isolated_client):
        """POST /dashboard/setup with mismatched passwords shows error."""
        response = isolated_client.post(
            "/dashboard/setup",
            data={"password": "password123", "confirm_password": "different123"},
        )

        assert response.status_code == 200
        assert b"Passwords do not match" in response.content

    def test_setup_post_password_min_length(self, isolated_client):
        """POST /dashboard/setup with short password shows error."""
        response = isolated_client.post(
            "/dashboard/setup", data={"password": "short", "confirm_password": "short"}
        )

        assert response.status_code == 200
        assert b"at least 8 characters" in response.content

    def test_setup_post_success_redirects_to_login(self, isolated_client):
        """POST /dashboard/setup with valid password redirects to login."""
        response = isolated_client.post(
            "/dashboard/setup",
            data={
                "password": "validpassword123",
                "confirm_password": "validpassword123",
            },
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard/login"


class TestLoginFlow:
    """Tests for login functionality."""

    def test_login_page_renders(self, isolated_client):
        """GET /dashboard/login should render login form."""
        # First set up a password
        isolated_client.post(
            "/dashboard/setup",
            data={
                "password": "validpassword123",
                "confirm_password": "validpassword123",
            },
        )

        response = isolated_client.get("/dashboard/login")

        assert response.status_code == 200
        assert b"Krell Dashboard" in response.content

    def test_login_wrong_password_shows_error(self, isolated_client):
        """POST /dashboard/login with wrong password shows error."""
        # First set up a password
        isolated_client.post(
            "/dashboard/setup",
            data={
                "password": "validpassword123",
                "confirm_password": "validpassword123",
            },
        )

        response = isolated_client.post(
            "/dashboard/login", data={"password": "wrongpassword"}
        )

        assert response.status_code == 200
        assert b"Invalid password" in response.content

    def test_login_success_sets_cookie_and_redirects(self, isolated_client):
        """POST /dashboard/login with correct password sets cookie and redirects."""
        # First set up a password
        isolated_client.post(
            "/dashboard/setup",
            data={
                "password": "validpassword123",
                "confirm_password": "validpassword123",
            },
        )

        response = isolated_client.post(
            "/dashboard/login",
            data={"password": "validpassword123"},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"
        assert "krell_session" in response.cookies


class TestLogout:
    """Tests for logout functionality."""

    def test_logout_clears_cookie_and_redirects(self, isolated_client):
        """GET /dashboard/logout clears session and redirects to login."""
        # Setup and login first
        isolated_client.post(
            "/dashboard/setup",
            data={
                "password": "validpassword123",
                "confirm_password": "validpassword123",
            },
        )
        isolated_client.post("/dashboard/login", data={"password": "validpassword123"})

        response = isolated_client.get("/dashboard/logout", follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"] == "/dashboard/login"


class TestProtectedRoutes:
    """Tests for authentication on protected routes."""

    def test_dashboard_api_status_requires_auth(self, isolated_client):
        """GET /dashboard/api/status should require auth."""
        # Setup password first
        isolated_client.post(
            "/dashboard/setup",
            data={
                "password": "validpassword123",
                "confirm_password": "validpassword123",
            },
        )

        response = isolated_client.get("/dashboard/api/status")

        assert response.status_code == 401

    def test_dashboard_api_status_works_with_auth(self, isolated_client):
        """GET /dashboard/api/status should work when authenticated."""
        # Setup and login
        isolated_client.post(
            "/dashboard/setup",
            data={
                "password": "validpassword123",
                "confirm_password": "validpassword123",
            },
        )
        isolated_client.post("/dashboard/login", data={"password": "validpassword123"})

        response = isolated_client.get("/dashboard/api/status")

        assert response.status_code == 200

    def test_admin_reload_plugins_requires_auth(self, isolated_client):
        """POST /api/admin/reload-plugins should require auth."""
        response = isolated_client.post("/api/admin/reload-plugins")

        assert response.status_code == 401

    def test_admin_plugins_requires_auth(self, isolated_client):
        """GET /api/admin/plugins should require auth."""
        response = isolated_client.get("/api/admin/plugins")

        assert response.status_code == 401

    def test_admin_reload_agent_requires_auth(self, isolated_client):
        """POST /api/admin/reload-agent should require auth."""
        response = isolated_client.post("/api/admin/reload-agent")

        assert response.status_code == 401

    def test_dashboard_api_settings_get_requires_auth(self, isolated_client):
        """GET /dashboard/api/settings should require auth."""
        isolated_client.post(
            "/dashboard/setup",
            data={
                "password": "validpassword123",
                "confirm_password": "validpassword123",
            },
        )

        response = isolated_client.get("/dashboard/api/settings")

        assert response.status_code == 401

    def test_dashboard_api_plugins_requires_auth(self, isolated_client):
        """GET /dashboard/api/plugins should require auth."""
        isolated_client.post(
            "/dashboard/setup",
            data={
                "password": "validpassword123",
                "confirm_password": "validpassword123",
            },
        )

        response = isolated_client.get("/dashboard/api/plugins")

        assert response.status_code == 401


class TestFullFlow:
    """End-to-end authentication flow test."""

    def test_complete_auth_flow(self, isolated_client):
        """Test complete flow: setup -> login -> access -> logout -> denied."""
        # 1. Dashboard redirects to setup
        response = isolated_client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 307
        assert "/setup" in response.headers["location"]

        # 2. Setup password
        response = isolated_client.post(
            "/dashboard/setup",
            data={"password": "securepass123", "confirm_password": "securepass123"},
            follow_redirects=False,
        )
        assert response.status_code == 303

        # 3. Dashboard now redirects to login
        response = isolated_client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 307
        assert "/login" in response.headers["location"]

        # 4. Login
        response = isolated_client.post(
            "/dashboard/login",
            data={"password": "securepass123"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "krell_session" in response.cookies

        # 5. Access dashboard (now works)
        response = isolated_client.get("/dashboard")
        assert response.status_code == 200
        assert b"Krell Dashboard" in response.content

        # 6. Logout
        response = isolated_client.get("/dashboard/logout", follow_redirects=False)
        assert response.status_code == 307

        # 7. Dashboard redirects to login again
        response = isolated_client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 307
        assert "/login" in response.headers["location"]
