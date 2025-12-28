"""Plugin utilities for Krell plugins.

This module provides utilities that plugins can use to access their configuration
and other Krell services.
"""

from core.plugin_manager import get_config

__all__ = ["get_config"]
