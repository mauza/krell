"""
Tests for the plugin loader system.

Following TDD - tests written first, watched fail, then implementation added.
"""

import pytest
import tempfile
import os
import shutil
import time
import asyncio
from pathlib import Path
from core.plugin_loader import load_plugins


class TestPluginLoader:
    """Tests for PluginLoader class."""

    @pytest.fixture
    def temp_plugin_dir(self):
        """Create a temporary directory for test plugins."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        shutil.rmtree(temp_dir)

    def test_loads_valid_plugin_with_tool_decorator(self, temp_plugin_dir):
        """Test that PluginLoader can load a valid plugin file with @tool decorator."""
        # Create a valid plugin file
        plugin_file = Path(temp_plugin_dir) / "test_plugin.py"
        plugin_file.write_text("""
from strands import tool

@tool
def test_function(message: str) -> dict:
    '''A test tool function.'''
    return {"result": f"processed: {message}"}
""")

        # Create plugin loader
        loader = PluginLoader(plugin_dir=temp_plugin_dir)

        # Load plugins
        loader.load_plugins()

        # Verify the plugin was loaded
        metadata = loader.get_plugin_metadata()
        assert len(metadata) == 1
        assert metadata[0]["filename"] == "test_plugin.py"
        assert "test_function" in metadata[0]["functions"]
        assert metadata[0]["status"] == "loaded"
        assert metadata[0]["errors"] is None

    def test_handles_syntax_errors_gracefully(self, temp_plugin_dir):
        """Test that PluginLoader handles syntax errors without crashing."""
        # Create a plugin file with syntax error
        plugin_file = Path(temp_plugin_dir) / "broken_plugin.py"
        plugin_file.write_text("""
from strands import tool

@tool
def broken_function(message: str) -> dict:
    '''A broken tool function.'''
    return {"result": f"processed: {message}"  # Missing closing brace
""")

        # Create plugin loader
        loader = PluginLoader(plugin_dir=temp_plugin_dir)

        # Load plugins - should not crash
        loader.load_plugins()

        # Verify the plugin was tracked with error status
        metadata = loader.get_plugin_metadata()
        assert len(metadata) == 1
        assert metadata[0]["filename"] == "broken_plugin.py"
        assert metadata[0]["status"] == "error"
        assert metadata[0]["errors"] is not None
        assert len(metadata[0]["functions"]) == 0

    def test_handles_plugin_without_tool_decorator(self, temp_plugin_dir):
        """Test that PluginLoader handles plugins without @tool decorator."""
        # Create a valid Python file but without @tool decorator
        plugin_file = Path(temp_plugin_dir) / "no_tool_plugin.py"
        plugin_file.write_text("""
def regular_function(message: str) -> dict:
    '''A regular function without @tool decorator.'''
    return {"result": f"processed: {message}"}
""")

        # Create plugin loader
        loader = PluginLoader(plugin_dir=temp_plugin_dir)

        # Load plugins
        loader.load_plugins()

        # Verify the plugin was loaded but found no tools
        metadata = loader.get_plugin_metadata()
        assert len(metadata) == 1
        assert metadata[0]["filename"] == "no_tool_plugin.py"
        assert metadata[0]["status"] == "loaded"
        assert metadata[0]["errors"] is None
        assert len(metadata[0]["functions"]) == 0  # No @tool functions found

    def test_handles_import_errors(self, temp_plugin_dir):
        """Test that PluginLoader handles import errors gracefully."""
        # Create a plugin file that imports a non-existent module
        plugin_file = Path(temp_plugin_dir) / "import_error_plugin.py"
        plugin_file.write_text("""
from strands import tool
from nonexistent_module import something

@tool
def test_function(message: str) -> dict:
    '''A test tool function.'''
    return {"result": something(message)}
""")

        # Create plugin loader
        loader = PluginLoader(plugin_dir=temp_plugin_dir)

        # Load plugins - should not crash
        loader.load_plugins()

        # Verify the plugin was tracked with error status
        metadata = loader.get_plugin_metadata()
        assert len(metadata) == 1
        assert metadata[0]["filename"] == "import_error_plugin.py"
        assert metadata[0]["status"] == "error"
        assert metadata[0]["errors"] is not None
        assert "nonexistent_module" in metadata[0]["errors"]
        assert len(metadata[0]["functions"]) == 0

    def test_returns_correct_metadata_structure(self, temp_plugin_dir):
        """Test that plugin metadata has correct structure with all required fields."""
        # Create a valid plugin
        plugin_file = Path(temp_plugin_dir) / "meta_test.py"
        plugin_file.write_text("""
from strands import tool

@tool
def tool_one(x: str) -> str:
    return x

@tool
def tool_two(y: int) -> int:
    return y * 2
""")

        # Create plugin loader
        loader = PluginLoader(plugin_dir=temp_plugin_dir)
        loader.load_plugins()

        # Verify metadata structure
        metadata = loader.get_plugin_metadata()
        assert len(metadata) == 1

        plugin_meta = metadata[0]
        assert "filename" in plugin_meta
        assert "functions" in plugin_meta
        assert "load_time" in plugin_meta
        assert "status" in plugin_meta
        assert "errors" in plugin_meta

        # Verify values
        assert plugin_meta["filename"] == "meta_test.py"
        assert len(plugin_meta["functions"]) == 2
        assert "tool_one" in plugin_meta["functions"]
        assert "tool_two" in plugin_meta["functions"]
        assert plugin_meta["status"] == "loaded"
        assert plugin_meta["errors"] is None
        assert isinstance(plugin_meta["load_time"], str)  # ISO timestamp


class TestPluginHotReload:
    """Tests for hot reload functionality with file watching."""

    @pytest.fixture
    def temp_plugin_dir(self):
        """Create a temporary directory for test plugins."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_plugin_auto_reloads_when_file_modified(self, temp_plugin_dir):
        """Test that plugin automatically reloads when file is modified."""
        # Create initial plugin file
        plugin_file = Path(temp_plugin_dir) / "dynamic_plugin.py"
        plugin_file.write_text("""
from strands import tool

@tool
def version_one() -> dict:
    '''Version 1 of the tool.'''
    return {"version": 1}
""")

        # Create plugin loader with hot reload enabled
        loader = PluginLoader(plugin_dir=temp_plugin_dir)
        loader.load_plugins()
        loader.start_watching()

        # Verify initial load
        tools = loader.get_tools()
        assert len(tools) == 1
        assert tools[0].tool_name == "version_one"

        # Wait for watchdog to fully start before making changes
        await asyncio.sleep(1.0)

        # Get initial load time
        initial_metadata = loader.get_plugin_metadata()
        initial_load_time = initial_metadata[0]["load_time"]

        # Modify plugin file with explicit flush
        with open(plugin_file, "w") as f:
            f.write("""
from strands import tool

@tool
def version_two() -> dict:
    '''Version 2 of the tool.'''
    return {"version": 2}
""")
            f.flush()
            os.fsync(f.fileno())

        # Poll for reload completion by checking load_time change (max 5 seconds)
        reloaded = False
        for attempt in range(50):
            await asyncio.sleep(0.1)
            current_metadata = loader.get_plugin_metadata()
            if (
                len(current_metadata) > 0
                and current_metadata[0]["load_time"] != initial_load_time
            ):
                tools = loader.get_tools()
                if len(tools) == 1 and tools[0].tool_name == "version_two":
                    reloaded = True
                    break

        assert reloaded, (
            f"Plugin did not reload after 5 seconds. Load time: {initial_load_time}"
        )

        # Verify plugin was reloaded with new function
        tools = loader.get_tools()
        assert len(tools) == 1
        assert tools[0].tool_name == "version_two"

        # Cleanup
        loader.stop_watching()

    @pytest.mark.asyncio
    async def test_debouncing_prevents_multiple_rapid_reloads(self, temp_plugin_dir):
        """Test that multiple rapid file changes are debounced to single reload."""
        # Create initial plugin file
        plugin_file = Path(temp_plugin_dir) / "debounce_test.py"
        plugin_file.write_text("""
from strands import tool

@tool
def initial() -> dict:
    return {"version": 0}
""")

        # Create plugin loader with hot reload
        loader = PluginLoader(plugin_dir=temp_plugin_dir)
        loader.load_plugins()
        loader.start_watching()

        # Track reload count
        initial_metadata = loader.get_plugin_metadata()
        initial_load_time = initial_metadata[0]["load_time"]

        # Make multiple rapid changes
        for i in range(5):
            plugin_file.write_text(f"""
from strands import tool

@tool
def version_{i}() -> dict:
    return {{"version": {i}}}
""")
            await asyncio.sleep(0.1)  # 100ms between changes

        # Wait for debounce period to complete
        await asyncio.sleep(1.5)

        # Verify only one reload occurred (load_time changed once)
        final_metadata = loader.get_plugin_metadata()
        final_load_time = final_metadata[0]["load_time"]

        # Load time should have changed (indicating reload happened)
        assert final_load_time != initial_load_time

        # Should have the final version
        tools = loader.get_tools()
        assert len(tools) == 1
        assert tools[0].tool_name == "version_4"

        # Cleanup
        loader.stop_watching()

    @pytest.mark.asyncio
    async def test_plugin_deleted_unregisters_tools(self, temp_plugin_dir):
        """Test that deleting a plugin file unregisters its tools."""
        # Create plugin file
        plugin_file = Path(temp_plugin_dir) / "temporary_plugin.py"
        plugin_file.write_text("""
from strands import tool

@tool
def temporary_tool() -> dict:
    return {"status": "exists"}
""")

        # Create plugin loader with hot reload
        loader = PluginLoader(plugin_dir=temp_plugin_dir)
        loader.load_plugins()
        loader.start_watching()

        # Verify plugin loaded
        assert len(loader.get_tools()) == 1
        assert len(loader.get_plugin_metadata()) == 1

        # Wait a moment, then delete the plugin file
        await asyncio.sleep(0.1)
        plugin_file.unlink()

        # Wait for file system event to be processed
        await asyncio.sleep(1.5)

        # Verify plugin was unregistered
        assert len(loader.get_tools()) == 0
        # Metadata might still track it as deleted/error
        metadata = loader.get_plugin_metadata()
        if len(metadata) > 0:
            assert (
                metadata[0]["status"] == "unloaded" or metadata[0]["status"] == "error"
            )

        # Cleanup
        loader.stop_watching()

    @pytest.mark.asyncio
    async def test_thread_safe_reload_doesnt_interrupt_requests(self, temp_plugin_dir):
        """Test that reloading doesn't interrupt ongoing tool executions."""
        # Create plugin file
        plugin_file = Path(temp_plugin_dir) / "slow_plugin.py"
        plugin_file.write_text("""
from strands import tool
import time

@tool
def slow_operation() -> dict:
    '''A tool that takes time to execute.'''
    time.sleep(0.5)
    return {"completed": True}
""")

        # Create plugin loader with hot reload
        loader = PluginLoader(plugin_dir=temp_plugin_dir)
        loader.load_plugins()
        loader.start_watching()

        # Start a "request" using the tool
        tools = loader.get_tools()
        original_tool = tools[0]

        # Create a task that uses the tool
        async def use_tool():
            # Call the tool function
            result = original_tool()
            return result

        # Start the task
        task = asyncio.create_task(use_tool())

        # Immediately modify the plugin while task is running
        await asyncio.sleep(0.1)
        plugin_file.write_text("""
from strands import tool

@tool
def fast_operation() -> dict:
    '''A modified tool.'''
    return {"modified": True}
""")

        # Wait for both task completion and reload
        result = await task
        await asyncio.sleep(1.5)

        # Verify the original task completed successfully
        assert result["completed"] is True

        # Verify the plugin was reloaded
        tools = loader.get_tools()
        assert len(tools) == 1
        assert tools[0].tool_name == "fast_operation"

        # Cleanup
        loader.stop_watching()

    def test_manual_reload_method_works(self, temp_plugin_dir):
        """Test that manual reload method re-scans and reloads plugins."""
        # Create initial plugin file
        plugin_file = Path(temp_plugin_dir) / "manual_reload.py"
        plugin_file.write_text("""
from strands import tool

@tool
def original() -> dict:
    return {"version": "original"}
""")

        # Create plugin loader (without auto-watching)
        loader = PluginLoader(plugin_dir=temp_plugin_dir)
        loader.load_plugins()

        # Verify initial load
        tools = loader.get_tools()
        assert len(tools) == 1
        assert tools[0].tool_name == "original"

        # Modify the plugin file
        plugin_file.write_text("""
from strands import tool

@tool
def updated() -> dict:
    return {"version": "updated"}
""")

        # Manually trigger reload
        loader.reload_plugins()

        # Verify plugin was reloaded
        tools = loader.get_tools()
        assert len(tools) == 1
        assert tools[0].tool_name == "updated"

    @pytest.mark.asyncio
    async def test_new_plugin_added_is_detected(self, temp_plugin_dir):
        """Test that adding a new plugin file is detected and loaded."""
        # Create initial plugin
        plugin1 = Path(temp_plugin_dir) / "plugin1.py"
        plugin1.write_text("""
from strands import tool

@tool
def tool_one() -> dict:
    return {"id": 1}
""")

        # Create plugin loader with hot reload
        loader = PluginLoader(plugin_dir=temp_plugin_dir)
        loader.load_plugins()
        loader.start_watching()

        # Verify initial state
        assert len(loader.get_tools()) == 1
        assert len(loader.get_plugin_metadata()) == 1

        # Wait a moment, then add a new plugin file
        await asyncio.sleep(0.1)
        plugin2 = Path(temp_plugin_dir) / "plugin2.py"
        plugin2.write_text("""
from strands import tool

@tool
def tool_two() -> dict:
    return {"id": 2}
""")

        # Wait for detection and loading
        await asyncio.sleep(1.5)

        # Verify new plugin was detected and loaded
        assert len(loader.get_tools()) == 2
        assert len(loader.get_plugin_metadata()) == 2

        tool_names = [tool.tool_name for tool in loader.get_tools()]
        assert "tool_one" in tool_names
        assert "tool_two" in tool_names

        # Cleanup
        loader.stop_watching()


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
