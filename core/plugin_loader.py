"""
Plugin loader for Krell's tool system.

Automatically discovers and loads tools from the plugins directory.
"""

import importlib
import os
import logging
import time
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class PluginLoader:
    """Manages plugin loading and provides tools to the agent."""

    def __init__(self):
        self._tools = []
        self._metadata = []
        self.load_plugins()

    def load_plugins(self) -> List[Any]:
        """
        Load all plugin tools from the plugins directory.

        Returns:
            List of Strands Tool objects
        """
        tools = []
        metadata = []
        plugins_dir = os.path.join(os.path.dirname(__file__), "..", "plugins")

        # Get all Python files in plugins directory
        try:
            plugin_files = [
                f[:-3]
                for f in os.listdir(plugins_dir)
                if f.endswith(".py") and f != "__init__.py"
            ]
        except FileNotFoundError:
            logger.warning(f"Plugins directory not found: {plugins_dir}")
            self._tools = tools
            self._metadata = metadata
            return tools

        for plugin_name in plugin_files:
            plugin_meta = {
                "filename": f"{plugin_name}.py",
                "status": "loading",
                "tools": [],
                "error": None,
                "load_time": None,
            }

            try:
                start_time = time.time()
                # Import the plugin module
                module = importlib.import_module(f"plugins.{plugin_name}")

                # Find all functions decorated with @tool
                plugin_tools = []
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    # Check if it's a Strands tool (has __tool__ attribute)
                    if hasattr(attr, "__tool__") or (
                        callable(attr) and hasattr(attr, "__wrapped__")
                    ):
                        tools.append(attr)
                        plugin_tools.append(attr_name)
                        logger.info(f"Loaded tool: {attr_name} from {plugin_name}")

                plugin_meta["status"] = "loaded"
                plugin_meta["tools"] = plugin_tools
                plugin_meta["load_time"] = time.time() - start_time

            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_name}: {e}")
                plugin_meta["status"] = "error"
                plugin_meta["error"] = str(e)

            metadata.append(plugin_meta)

        self._tools = tools
        self._metadata = metadata
        logger.info(f"Loaded {len(tools)} tools from {len(plugin_files)} plugins")
        return tools

    def reload_plugins(self) -> List[Any]:
        """Reload all plugins and return the new tools list."""
        logger.info("Reloading plugins...")
        return self.load_plugins()

    def get_tools(self) -> List[Any]:
        """Get the currently loaded tools."""
        return self._tools

    def get_plugin_metadata(self) -> List[Dict[str, Any]]:
        """Get metadata about loaded plugins."""
        return self._metadata


def load_plugins() -> list:
    """
    Legacy function for backward compatibility.

    Returns:
        List of Strands Tool objects
    """
    return PluginLoader().get_tools()
