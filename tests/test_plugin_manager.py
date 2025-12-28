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
