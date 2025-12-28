# tests/test_plugin_manager.py
"""Tests for the plugin manager system."""

import pytest
import tempfile
import shutil
from pathlib import Path

from core.plugin_manager import PluginManifest, PluginConfigField


class TestPluginManifest:
    """Tests for plugin manifest parsing."""

    def test_parses_valid_manifest(self):
        """Test that a valid plugin.yaml is parsed correctly."""
        manifest_content = """
name: weather-plugin
version: 1.0.0
description: Get weather forecasts
author: Test Author
entry_point: weather_plugin.tools

config:
  api_key:
    type: secret
    required: true
    label: "API Key"
    description: "Your API key"
  
  units:
    type: choice
    options: ["imperial", "metric"]
    default: "imperial"
    label: "Units"

dependencies:
  - requests>=2.28.0
"""
        manifest = PluginManifest.from_yaml(manifest_content)

        assert manifest.name == "weather-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.description == "Get weather forecasts"
        assert manifest.author == "Test Author"
        assert manifest.entry_point == "weather_plugin.tools"
        assert len(manifest.config) == 2
        assert manifest.config["api_key"].type == "secret"
        assert manifest.config["api_key"].required is True
        assert manifest.config["units"].type == "choice"
        assert manifest.config["units"].options == ["imperial", "metric"]
        assert manifest.config["units"].default == "imperial"
        assert manifest.dependencies == ["requests>=2.28.0"]

    def test_manifest_requires_name_version_entry_point(self):
        """Test that manifest validation fails without required fields."""
        manifest_content = """
description: Missing required fields
"""
        with pytest.raises(ValueError) as exc_info:
            PluginManifest.from_yaml(manifest_content)

        assert (
            "name" in str(exc_info.value).lower()
            or "required" in str(exc_info.value).lower()
        )

    def test_config_field_types_validated(self):
        """Test that config field types are validated."""
        manifest_content = """
name: test-plugin
version: 1.0.0
entry_point: test.tools

config:
  bad_field:
    type: invalid_type
    label: "Bad Field"
"""
        with pytest.raises(ValueError) as exc_info:
            PluginManifest.from_yaml(manifest_content)

        assert (
            "type" in str(exc_info.value).lower()
            or "invalid" in str(exc_info.value).lower()
        )


class TestPluginRegistry:
    """Tests for plugin registry (tracking installed plugins)."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    def test_registry_creates_directory_structure(self, temp_data_dir):
        """Test that registry creates required directories on init."""
        from core.plugin_manager import PluginRegistry

        registry = PluginRegistry(temp_data_dir)

        assert (temp_data_dir / "plugins" / "installed").exists()
        assert (temp_data_dir / "plugins" / "config").exists()
        assert (temp_data_dir / "plugins" / "registry.yaml").exists()

    def test_registry_tracks_installed_plugin(self, temp_data_dir):
        """Test that registry can track an installed plugin."""
        from core.plugin_manager import PluginRegistry

        registry = PluginRegistry(temp_data_dir)

        registry.register_plugin(
            name="test-plugin",
            version="1.0.0",
            source="upload",
        )

        plugins = registry.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "test-plugin"
        assert plugins[0]["version"] == "1.0.0"
        assert plugins[0]["enabled"] is True  # Default enabled
        assert plugins[0]["source"] == "upload"

    def test_registry_persists_across_instances(self, temp_data_dir):
        """Test that registry state persists to disk."""
        from core.plugin_manager import PluginRegistry

        # First instance
        registry1 = PluginRegistry(temp_data_dir)
        registry1.register_plugin("persist-test", "2.0.0", "upload")

        # Second instance (simulate restart)
        registry2 = PluginRegistry(temp_data_dir)
        plugins = registry2.list_plugins()

        assert len(plugins) == 1
        assert plugins[0]["name"] == "persist-test"

    def test_registry_enable_disable_plugin(self, temp_data_dir):
        """Test enabling and disabling plugins."""
        from core.plugin_manager import PluginRegistry

        registry = PluginRegistry(temp_data_dir)
        registry.register_plugin("toggle-test", "1.0.0", "upload")

        # Disable
        registry.set_enabled("toggle-test", False)
        plugins = registry.list_plugins()
        assert plugins[0]["enabled"] is False

        # Enable
        registry.set_enabled("toggle-test", True)
        plugins = registry.list_plugins()
        assert plugins[0]["enabled"] is True

    def test_registry_unregister_plugin(self, temp_data_dir):
        """Test unregistering a plugin."""
        from core.plugin_manager import PluginRegistry

        registry = PluginRegistry(temp_data_dir)
        registry.register_plugin("to-remove", "1.0.0", "upload")

        assert len(registry.list_plugins()) == 1

        registry.unregister_plugin("to-remove")

        assert len(registry.list_plugins()) == 0


class TestPluginConfigStorage:
    """Tests for plugin configuration storage."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    def test_save_and_load_plugin_config(self, temp_data_dir):
        """Test saving and loading plugin configuration."""
        from core.plugin_manager import PluginConfigStorage

        storage = PluginConfigStorage(temp_data_dir / "plugins" / "config")

        config = {
            "api_key": "secret123",
            "units": "metric",
            "cache_duration": 300,
        }

        storage.save("weather-plugin", config)
        loaded = storage.load("weather-plugin")

        assert loaded == config

    def test_load_returns_empty_for_missing_config(self, temp_data_dir):
        """Test that loading missing config returns empty dict."""
        from core.plugin_manager import PluginConfigStorage

        storage = PluginConfigStorage(temp_data_dir / "plugins" / "config")

        loaded = storage.load("nonexistent-plugin")

        assert loaded == {}

    def test_config_validates_against_schema(self, temp_data_dir):
        """Test that config values are validated against manifest schema."""
        from core.plugin_manager import PluginConfigStorage, PluginManifest

        storage = PluginConfigStorage(temp_data_dir / "plugins" / "config")

        manifest = PluginManifest.from_yaml("""
name: test-plugin
version: 1.0.0
entry_point: test.tools
config:
  api_key:
    type: secret
    required: true
    label: "API Key"
  count:
    type: int
    default: 10
    label: "Count"
""")

        # Missing required field
        with pytest.raises(ValueError) as exc_info:
            storage.validate_config({"count": 5}, manifest)

        assert (
            "api_key" in str(exc_info.value).lower()
            or "required" in str(exc_info.value).lower()
        )

    def test_config_applies_defaults(self, temp_data_dir):
        """Test that default values are applied for missing optional fields."""
        from core.plugin_manager import PluginConfigStorage, PluginManifest

        storage = PluginConfigStorage(temp_data_dir / "plugins" / "config")

        manifest = PluginManifest.from_yaml("""
name: test-plugin
version: 1.0.0
entry_point: test.tools
config:
  api_key:
    type: secret
    required: true
    label: "API Key"
  units:
    type: choice
    options: ["imperial", "metric"]
    default: "imperial"
    label: "Units"
""")

        config = {"api_key": "secret123"}
        result = storage.apply_defaults(config, manifest)

        assert result["api_key"] == "secret123"
        assert result["units"] == "imperial"
