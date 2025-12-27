"""
Tests for the new plugin loader function implementation.
"""

import pytest


def test_plugin_loader_loads_entity_tools():
    """Test that plugin loader loads entity management tools."""
    from core.plugin_loader import load_plugins

    tools = load_plugins()

    tool_names = [t.__name__ for t in tools]

    # Check for new tools
    assert "create_entity" in tool_names
    assert "update_entity" in tool_names
    assert "search_entities" in tool_names
    assert "create_event" in tool_names
    assert "search_events" in tool_names
    assert "create_journal" in tool_names
    assert "search_journals" in tool_names
    assert "create_rating" in tool_names
    assert "get_ratings" in tool_names

    # Old tools should be removed
    assert "save_journal_entry" not in tool_names
    assert "get_journal_entries" not in tool_names
    assert "save_rating" not in tool_names  # Old scoring tool function


def test_plugin_loader_excludes_old_tools():
    """Test that old tools are not loaded."""
    from core.plugin_loader import load_plugins

    tools = load_plugins()
    tool_names = [t.__name__ for t in tools]

    # Make sure example_tool is not loaded
    assert "example_function" not in tool_names
