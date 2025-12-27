"""Tests for agent caching and reload functionality."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_get_krell_agent_caching():
    """Test that get_krell_agent returns cached instance."""
    # Clear cache first
    import api.routes

    api.routes._krell_agent = None

    with (
        patch("api.routes.KrellAgent") as mock_agent_class,
        patch("api.routes.Database") as mock_db_class,
        patch("api.routes.plugin_loader") as mock_plugin_loader,
    ):
        # Setup mocks
        mock_agent = Mock()
        mock_agent_class.create = AsyncMock(return_value=mock_agent)
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_plugin_loader.get_tools.return_value = []

        from api.routes import get_krell_agent

        # First call should create agent
        agent1 = await get_krell_agent()
        assert agent1 == mock_agent
        assert mock_agent_class.create.call_count == 1

        # Second call should return cached agent
        agent2 = await get_krell_agent()
        assert agent2 == mock_agent
        assert agent2 is agent1  # Same instance
        assert mock_agent_class.create.call_count == 1  # Not called again


@pytest.mark.asyncio
async def test_reload_krell_agent():
    """Test that reload_krell_agent creates new instance."""
    # Clear cache first
    import api.routes

    api.routes._krell_agent = None

    with (
        patch("api.routes.KrellAgent") as mock_agent_class,
        patch("api.routes.Database") as mock_db_class,
        patch("api.routes.plugin_loader") as mock_plugin_loader,
    ):
        # Setup mocks for two different agent instances
        mock_agent1 = Mock(llm_model="model1", llm_endpoint="http://endpoint1")
        mock_agent2 = Mock(llm_model="model2", llm_endpoint="http://endpoint2")
        mock_agent_class.create = AsyncMock(side_effect=[mock_agent1, mock_agent2])

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_plugin_loader.get_tools.return_value = []

        from api.routes import get_krell_agent, reload_krell_agent

        # Create first agent
        agent1 = await get_krell_agent()
        assert agent1 == mock_agent1
        assert agent1.llm_model == "model1"

        # Reload should create new agent
        agent2 = await reload_krell_agent()
        assert agent2 == mock_agent2
        assert agent2 is not agent1  # Different instance
        assert hasattr(agent2, "llm_model") and agent2.llm_model == "model2"
        assert mock_agent_class.create.call_count == 2


@pytest.mark.asyncio
async def test_reload_krell_agent_updates_cache():
    """Test that reload updates the cache correctly."""
    # Clear cache first
    import api.routes

    api.routes._krell_agent = None

    with (
        patch("api.routes.KrellAgent") as mock_agent_class,
        patch("api.routes.Database") as mock_db_class,
        patch("api.routes.plugin_loader") as mock_plugin_loader,
    ):
        # Setup mocks for two different agent instances
        mock_agent1 = Mock(llm_model="model1")
        mock_agent2 = Mock(llm_model="model2")
        mock_agent_class.create = AsyncMock(side_effect=[mock_agent1, mock_agent2])

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_plugin_loader.get_tools.return_value = []

        from api.routes import get_krell_agent, reload_krell_agent

        # Create first agent
        agent1 = await get_krell_agent()
        assert agent1 == mock_agent1
        assert agent1.llm_model == "model1"

        # Reload
        await reload_krell_agent()

        # Next get should return reloaded agent
        agent3 = await get_krell_agent()
        assert agent3 == mock_agent2
        assert agent3 is not agent1
        assert agent3.llm_model == "model2"


@pytest.mark.asyncio
async def test_concurrent_get_krell_agent():
    """Test concurrent calls to get_krell_agent."""
    # Clear cache first
    import api.routes

    api.routes._krell_agent = None

    with (
        patch("api.routes.KrellAgent") as mock_agent_class,
        patch("api.routes.Database") as mock_db_class,
        patch("api.routes.plugin_loader") as mock_plugin_loader,
    ):
        # Setup mocks
        mock_agent = Mock()
        mock_agent_class.create = AsyncMock(return_value=mock_agent)

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_plugin_loader.get_tools.return_value = []

        from api.routes import get_krell_agent

        # Make multiple concurrent calls
        agents = await asyncio.gather(
            get_krell_agent(),
            get_krell_agent(),
            get_krell_agent(),
        )

        # All should return same instance
        assert all(a == mock_agent for a in agents)
        assert all(a is agents[0] for a in agents)
        # Should only create agent once despite concurrent calls
        assert mock_agent_class.create.call_count == 1


@pytest.mark.asyncio
async def test_concurrent_reload_krell_agent():
    """Test concurrent calls to reload_krell_agent."""
    # Clear cache first
    import api.routes

    api.routes._krell_agent = None

    with (
        patch("api.routes.KrellAgent") as mock_agent_class,
        patch("api.routes.Database") as mock_db_class,
        patch("api.routes.plugin_loader") as mock_plugin_loader,
    ):
        # Setup mocks - create agent first, then reload creates new one
        mock_agent1 = Mock(llm_model="model1")
        mock_agent2 = Mock(llm_model="model2")
        mock_agent_class.create = AsyncMock(side_effect=[mock_agent1, mock_agent2])

        mock_db = Mock()
        mock_db_class.return_value = mock_db
        mock_plugin_loader.get_tools.return_value = []

        from api.routes import get_krell_agent, reload_krell_agent

        # Create first agent
        await get_krell_agent()

        # Make multiple concurrent reload calls
        agents = await asyncio.gather(
            reload_krell_agent(),
            reload_krell_agent(),
            reload_krell_agent(),
        )

        # All should return the reloaded agent
        assert all(a == mock_agent2 for a in agents)
        assert all(a is agents[0] for a in agents)
        # Should only create new agent once despite concurrent reloads
        assert mock_agent_class.create.call_count == 2  # 1 for initial, 1 for reload


@pytest.mark.asyncio
async def test_dashboard_update_settings_triggers_reload():
    """Test that dashboard settings update triggers agent reload."""
    with (
        patch("main.Database") as mock_db_class,
        patch("main.reload_krell_agent") as mock_reload,
        patch("main.db") as mock_legacy_db,
    ):
        # Setup mocks
        mock_db = Mock()
        mock_db.set_setting = AsyncMock()
        mock_db_class.return_value = mock_db

        mock_agent = Mock(llm_model="new-model", llm_endpoint="http://new-endpoint")
        mock_reload.return_value = mock_agent

        mock_legacy_db.db_path = "/test/db/path"

        from main import dashboard_update_settings

        # Call update settings
        result = await dashboard_update_settings(
            llm_endpoint="http://new-endpoint",
            llm_model="new-model",
            llm_provider="ollama",
            api_key="new-key",
        )

        # Verify settings were updated
        assert mock_db.set_setting.call_count >= 3
        mock_db.set_setting.assert_any_call("llm_endpoint", "http://new-endpoint")
        mock_db.set_setting.assert_any_call("llm_model", "new-model")
        mock_db.set_setting.assert_any_call("llm_provider", "ollama")

        # Verify reload was called
        mock_reload.assert_called_once()

        # Verify success response
        assert result["success"] is True
        assert "reloaded" in result["message"].lower()


@pytest.mark.asyncio
async def test_dashboard_update_settings_with_masked_api_key():
    """Test that dashboard settings handles masked API key correctly."""
    with (
        patch("main.Database") as mock_db_class,
        patch("main.reload_krell_agent") as mock_reload,
        patch("main.db") as mock_legacy_db,
    ):
        # Setup mocks
        mock_db = Mock()
        mock_db.set_setting = AsyncMock()
        mock_db_class.return_value = mock_db

        mock_agent = Mock(llm_model="new-model", llm_endpoint="http://new-endpoint")
        mock_reload.return_value = mock_agent

        mock_legacy_db.db_path = "/test/db/path"

        from main import dashboard_update_settings

        # Call update settings with masked API key (should not update)
        result = await dashboard_update_settings(
            llm_endpoint="http://new-endpoint",
            llm_model="new-model",
            llm_provider="ollama",
            api_key="••••••••",  # Masked key
        )

        # Verify settings were updated (except API key)
        assert mock_db.set_setting.call_count == 3  # Only 3 settings, not API key
        mock_db.set_setting.assert_any_call("llm_endpoint", "http://new-endpoint")
        mock_db.set_setting.assert_any_call("llm_model", "new-model")
        mock_db.set_setting.assert_any_call("llm_provider", "ollama")

        # Verify reload was called
        mock_reload.assert_called_once()

        # Verify success response
        assert result["success"] is True


@pytest.mark.asyncio
async def test_dashboard_update_settings_reload_failure():
    """Test that dashboard settings handles reload failure gracefully."""
    with (
        patch("main.Database") as mock_db_class,
        patch("main.reload_krell_agent") as mock_reload,
        patch("main.db") as mock_legacy_db,
    ):
        # Setup mocks
        mock_db = Mock()
        mock_db.set_setting = AsyncMock()
        mock_db_class.return_value = mock_db

        # Simulate reload failure
        mock_reload.side_effect = Exception("Reload failed")

        mock_legacy_db.db_path = "/test/db/path"

        from main import dashboard_update_settings

        # Call update settings
        result = await dashboard_update_settings(
            llm_endpoint="http://new-endpoint",
            llm_model="new-model",
            llm_provider="ollama",
            api_key="new-key",
        )

        # Verify settings were updated
        assert mock_db.set_setting.call_count >= 3

        # Verify reload was called
        mock_reload.assert_called_once()

        # Verify warning response
        assert result["success"] is True
        assert "warning" in result
        assert result["warning"] is True
        assert "reload failed" in result["message"].lower()


@pytest.mark.asyncio
async def test_reload_agent_endpoint():
    """Test the admin reload agent endpoint."""
    with patch("api.routes.reload_krell_agent") as mock_reload:
        mock_agent = Mock(llm_model="test-model", llm_endpoint="http://test")
        mock_reload.return_value = mock_agent

        from api.routes import reload_agent

        response = await reload_agent()

        assert response["success"] is True
        assert response["model"] == "test-model"
        assert response["endpoint"] == "http://test"
        assert "reloaded successfully" in response["message"].lower()
        mock_reload.assert_called_once()


@pytest.mark.asyncio
async def test_reload_agent_endpoint_failure():
    """Test the admin reload agent endpoint handles failures."""
    with patch("api.routes.reload_krell_agent") as mock_reload:
        # Simulate reload failure
        mock_reload.side_effect = Exception("Reload failed")

        from api.routes import reload_agent

        with pytest.raises(HTTPException) as exc_info:
            await reload_agent()

        assert exc_info.value.status_code == 500
        assert "Reload failed" in exc_info.value.detail
        mock_reload.assert_called_once()


@pytest.mark.asyncio
async def test_agent_cache_with_tools():
    """Test that cached agent has tools properly attached."""
    # Clear cache first
    import api.routes

    api.routes._krell_agent = None

    with (
        patch("api.routes.KrellAgent") as mock_agent_class,
        patch("api.routes.Database") as mock_db_class,
        patch("api.routes.plugin_loader") as mock_plugin_loader,
    ):
        # Setup mocks
        mock_agent = Mock()
        mock_agent._strands_agent = Mock()
        mock_agent._strands_agent.tools = []
        mock_agent_class.create = AsyncMock(return_value=mock_agent)

        mock_db = Mock()
        mock_db_class.return_value = mock_db

        # Mock tools
        mock_tool1 = Mock(tool_name="tool1")
        mock_tool2 = Mock(tool_name="tool2")
        mock_plugin_loader.get_tools.return_value = [mock_tool1, mock_tool2]

        from api.routes import get_krell_agent

        # Get agent
        agent = await get_krell_agent()

        # Verify tools were attached
        assert agent._strands_agent.tools == [mock_tool1, mock_tool2]
        mock_plugin_loader.get_tools.assert_called_once()


@pytest.mark.asyncio
async def test_reload_preserves_tools():
    """Test that reloaded agent has tools properly attached."""
    # Clear cache first
    import api.routes

    api.routes._krell_agent = None

    with (
        patch("api.routes.KrellAgent") as mock_agent_class,
        patch("api.routes.Database") as mock_db_class,
        patch("api.routes.plugin_loader") as mock_plugin_loader,
    ):
        # Setup mocks for two agent instances
        mock_agent1 = Mock()
        mock_agent1._strands_agent = Mock()
        mock_agent1._strands_agent.tools = []

        mock_agent2 = Mock()
        mock_agent2._strands_agent = Mock()
        mock_agent2._strands_agent.tools = []

        mock_agent_class.create = AsyncMock(side_effect=[mock_agent1, mock_agent2])

        mock_db = Mock()
        mock_db_class.return_value = mock_db

        # Mock tools
        mock_tool1 = Mock(tool_name="tool1")
        mock_tool2 = Mock(tool_name="tool2")
        mock_plugin_loader.get_tools.return_value = [mock_tool1, mock_tool2]

        from api.routes import get_krell_agent, reload_krell_agent

        # Create first agent
        agent1 = await get_krell_agent()
        assert agent1._strands_agent.tools == [mock_tool1, mock_tool2]

        # Reload
        agent2 = await reload_krell_agent()

        # Verify reloaded agent also has tools
        assert agent2._strands_agent.tools == [mock_tool1, mock_tool2]
        # Should have called get_tools twice (once for each agent creation)
        assert mock_plugin_loader.get_tools.call_count == 2
