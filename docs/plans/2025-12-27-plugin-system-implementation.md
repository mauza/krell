# Plugin System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement runtime plugin management that allows users to install, configure, and manage plugins without rebuilding Docker containers.

**Architecture:** A new `PluginManager` class handles plugin installation, configuration, and lifecycle. Plugins are stored in `data/plugins/` with a manifest-based configuration system. The dashboard provides UI for upload, configuration, and enable/disable functionality.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, PyYAML, aiofiles, zipfile/tarfile

---

## Task 1: Create Plugin Manifest Schema

**Files:**
- Create: `core/plugin_manager.py`
- Test: `tests/test_plugin_manager.py`

**Step 1: Write the failing test for manifest parsing**

```python
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
        
        assert "name" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()

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
        
        assert "type" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugin_manager.py::TestPluginManifest -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'core.plugin_manager'" or similar

**Step 3: Write minimal implementation**

```python
# core/plugin_manager.py
"""
Plugin manager for Krell's runtime plugin system.

Handles plugin installation, configuration, and lifecycle management.
"""

import yaml
from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, field
from pathlib import Path


# Valid config field types
ConfigFieldType = Literal["string", "secret", "bool", "int", "float", "choice", "list"]
VALID_CONFIG_TYPES = {"string", "secret", "bool", "int", "float", "choice", "list"}


@dataclass
class PluginConfigField:
    """Schema for a single plugin configuration field."""
    
    type: ConfigFieldType
    label: str
    required: bool = False
    default: Any = None
    description: str = ""
    options: List[str] = field(default_factory=list)  # For 'choice' type
    
    def __post_init__(self):
        if self.type not in VALID_CONFIG_TYPES:
            raise ValueError(
                f"Invalid config field type '{self.type}'. "
                f"Must be one of: {', '.join(VALID_CONFIG_TYPES)}"
            )
        if self.type == "choice" and not self.options:
            raise ValueError("Config field of type 'choice' requires 'options' list")


@dataclass
class PluginManifest:
    """Parsed plugin manifest from plugin.yaml."""
    
    name: str
    version: str
    entry_point: str
    description: str = ""
    author: str = ""
    config: Dict[str, PluginConfigField] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    
    @classmethod
    def from_yaml(cls, yaml_content: str) -> "PluginManifest":
        """Parse a plugin manifest from YAML content."""
        data = yaml.safe_load(yaml_content)
        
        if not data:
            raise ValueError("Empty manifest")
        
        # Validate required fields
        required_fields = ["name", "version", "entry_point"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        
        # Parse config fields
        config = {}
        if "config" in data and data["config"]:
            for field_name, field_data in data["config"].items():
                config[field_name] = PluginConfigField(
                    type=field_data.get("type", "string"),
                    label=field_data.get("label", field_name),
                    required=field_data.get("required", False),
                    default=field_data.get("default"),
                    description=field_data.get("description", ""),
                    options=field_data.get("options", []),
                )
        
        return cls(
            name=data["name"],
            version=data["version"],
            entry_point=data["entry_point"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            config=config,
            dependencies=data.get("dependencies", []),
        )
    
    @classmethod
    def from_file(cls, path: Path) -> "PluginManifest":
        """Load manifest from a plugin.yaml file."""
        with open(path, "r") as f:
            return cls.from_yaml(f.read())
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugin_manager.py::TestPluginManifest -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/plugin_manager.py tests/test_plugin_manager.py
git commit -m "feat: add plugin manifest schema and parser"
```

---

## Task 2: Create Plugin Registry

**Files:**
- Modify: `core/plugin_manager.py`
- Test: `tests/test_plugin_manager.py`

**Step 1: Write the failing test for registry**

```python
# Add to tests/test_plugin_manager.py

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugin_manager.py::TestPluginRegistry -v`
Expected: FAIL with import error

**Step 3: Write minimal implementation**

```python
# Add to core/plugin_manager.py

from datetime import datetime
import os


@dataclass
class PluginRegistryEntry:
    """Entry in the plugin registry."""
    
    name: str
    version: str
    source: str
    installed_at: str
    enabled: bool = True


class PluginRegistry:
    """Manages the registry of installed plugins."""
    
    def __init__(self, data_dir: Path):
        """Initialize the plugin registry.
        
        Args:
            data_dir: Base data directory (e.g., ./data)
        """
        self.data_dir = Path(data_dir)
        self.plugins_dir = self.data_dir / "plugins"
        self.installed_dir = self.plugins_dir / "installed"
        self.config_dir = self.plugins_dir / "config"
        self.registry_file = self.plugins_dir / "registry.yaml"
        
        self._ensure_directories()
        self._plugins: Dict[str, PluginRegistryEntry] = {}
        self._load_registry()
    
    def _ensure_directories(self):
        """Create required directories if they don't exist."""
        self.installed_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.registry_file.exists():
            self._save_registry()
    
    def _load_registry(self):
        """Load registry from disk."""
        if self.registry_file.exists():
            with open(self.registry_file, "r") as f:
                data = yaml.safe_load(f) or {}
            
            plugins_data = data.get("plugins", {})
            for name, entry_data in plugins_data.items():
                self._plugins[name] = PluginRegistryEntry(
                    name=name,
                    version=entry_data.get("version", "0.0.0"),
                    source=entry_data.get("source", "unknown"),
                    installed_at=entry_data.get("installed_at", ""),
                    enabled=entry_data.get("enabled", True),
                )
    
    def _save_registry(self):
        """Save registry to disk."""
        data = {
            "plugins": {
                name: {
                    "version": entry.version,
                    "source": entry.source,
                    "installed_at": entry.installed_at,
                    "enabled": entry.enabled,
                }
                for name, entry in self._plugins.items()
            }
        }
        
        with open(self.registry_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False)
    
    def register_plugin(self, name: str, version: str, source: str):
        """Register a newly installed plugin."""
        self._plugins[name] = PluginRegistryEntry(
            name=name,
            version=version,
            source=source,
            installed_at=datetime.utcnow().isoformat() + "Z",
            enabled=True,
        )
        self._save_registry()
    
    def unregister_plugin(self, name: str):
        """Remove a plugin from the registry."""
        if name in self._plugins:
            del self._plugins[name]
            self._save_registry()
    
    def set_enabled(self, name: str, enabled: bool):
        """Enable or disable a plugin."""
        if name in self._plugins:
            self._plugins[name].enabled = enabled
            self._save_registry()
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all registered plugins."""
        return [
            {
                "name": entry.name,
                "version": entry.version,
                "source": entry.source,
                "installed_at": entry.installed_at,
                "enabled": entry.enabled,
            }
            for entry in self._plugins.values()
        ]
    
    def get_plugin(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific plugin's registry entry."""
        if name in self._plugins:
            entry = self._plugins[name]
            return {
                "name": entry.name,
                "version": entry.version,
                "source": entry.source,
                "installed_at": entry.installed_at,
                "enabled": entry.enabled,
            }
        return None
    
    def is_enabled(self, name: str) -> bool:
        """Check if a plugin is enabled."""
        return name in self._plugins and self._plugins[name].enabled
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugin_manager.py::TestPluginRegistry -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/plugin_manager.py tests/test_plugin_manager.py
git commit -m "feat: add plugin registry for tracking installed plugins"
```

---

## Task 3: Create Plugin Configuration Storage

**Files:**
- Modify: `core/plugin_manager.py`
- Test: `tests/test_plugin_manager.py`

**Step 1: Write the failing test for config storage**

```python
# Add to tests/test_plugin_manager.py

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
        
        assert "api_key" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()

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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugin_manager.py::TestPluginConfigStorage -v`
Expected: FAIL with import error

**Step 3: Write minimal implementation**

```python
# Add to core/plugin_manager.py

class PluginConfigStorage:
    """Manages plugin configuration files."""
    
    def __init__(self, config_dir: Path):
        """Initialize config storage.
        
        Args:
            config_dir: Directory for plugin config files
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def _config_path(self, plugin_name: str) -> Path:
        """Get the config file path for a plugin."""
        return self.config_dir / f"{plugin_name}.yaml"
    
    def save(self, plugin_name: str, config: Dict[str, Any]):
        """Save plugin configuration."""
        with open(self._config_path(plugin_name), "w") as f:
            yaml.dump(config, f, default_flow_style=False)
    
    def load(self, plugin_name: str) -> Dict[str, Any]:
        """Load plugin configuration."""
        path = self._config_path(plugin_name)
        if path.exists():
            with open(path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}
    
    def delete(self, plugin_name: str):
        """Delete plugin configuration."""
        path = self._config_path(plugin_name)
        if path.exists():
            path.unlink()
    
    def validate_config(self, config: Dict[str, Any], manifest: PluginManifest) -> None:
        """Validate config against manifest schema.
        
        Raises:
            ValueError: If required fields are missing or types are invalid
        """
        for field_name, field_schema in manifest.config.items():
            if field_schema.required and field_name not in config:
                raise ValueError(f"Required config field '{field_name}' is missing")
            
            if field_name in config:
                value = config[field_name]
                
                # Type validation
                if field_schema.type == "int" and not isinstance(value, int):
                    raise ValueError(f"Config field '{field_name}' must be an integer")
                elif field_schema.type == "float" and not isinstance(value, (int, float)):
                    raise ValueError(f"Config field '{field_name}' must be a number")
                elif field_schema.type == "bool" and not isinstance(value, bool):
                    raise ValueError(f"Config field '{field_name}' must be a boolean")
                elif field_schema.type == "choice" and value not in field_schema.options:
                    raise ValueError(
                        f"Config field '{field_name}' must be one of: {field_schema.options}"
                    )
    
    def apply_defaults(self, config: Dict[str, Any], manifest: PluginManifest) -> Dict[str, Any]:
        """Apply default values for missing optional fields."""
        result = dict(config)
        
        for field_name, field_schema in manifest.config.items():
            if field_name not in result and field_schema.default is not None:
                result[field_name] = field_schema.default
        
        return result
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugin_manager.py::TestPluginConfigStorage -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/plugin_manager.py tests/test_plugin_manager.py
git commit -m "feat: add plugin configuration storage with validation"
```

---

## Task 4: Create Plugin Installer (Package Extraction)

**Files:**
- Modify: `core/plugin_manager.py`
- Test: `tests/test_plugin_manager.py`

**Step 1: Write the failing test for package installation**

```python
# Add to tests/test_plugin_manager.py
import zipfile
import io

class TestPluginInstaller:
    """Tests for plugin package installation."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    def _create_plugin_zip(self, manifest_content: str, module_content: str = "") -> bytes:
        """Helper to create a valid plugin zip file."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("plugin.yaml", manifest_content)
            if module_content:
                zf.writestr("my_plugin/__init__.py", "")
                zf.writestr("my_plugin/tools.py", module_content)
        return buffer.getvalue()

    def test_installs_valid_plugin_package(self, temp_data_dir):
        """Test installing a valid plugin zip package."""
        from core.plugin_manager import PluginInstaller, PluginRegistry
        
        registry = PluginRegistry(temp_data_dir)
        installer = PluginInstaller(registry)
        
        manifest = """
name: test-plugin
version: 1.0.0
description: A test plugin
entry_point: my_plugin.tools
"""
        module = '''
from strands import tool

@tool
def test_tool() -> dict:
    """A test tool."""
    return {"status": "ok"}
'''
        package_bytes = self._create_plugin_zip(manifest, module)
        
        result = installer.install(package_bytes)
        
        assert result["success"] is True
        assert result["name"] == "test-plugin"
        assert result["version"] == "1.0.0"
        
        # Verify files were extracted
        plugin_dir = temp_data_dir / "plugins" / "installed" / "test-plugin"
        assert plugin_dir.exists()
        assert (plugin_dir / "plugin.yaml").exists()
        assert (plugin_dir / "my_plugin" / "tools.py").exists()

    def test_rejects_package_without_manifest(self, temp_data_dir):
        """Test that packages without plugin.yaml are rejected."""
        from core.plugin_manager import PluginInstaller, PluginRegistry
        
        registry = PluginRegistry(temp_data_dir)
        installer = PluginInstaller(registry)
        
        # Create zip without plugin.yaml
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("some_file.py", "# no manifest")
        
        result = installer.install(buffer.getvalue())
        
        assert result["success"] is False
        assert "manifest" in result["error"].lower() or "plugin.yaml" in result["error"].lower()

    def test_rejects_invalid_manifest(self, temp_data_dir):
        """Test that packages with invalid manifests are rejected."""
        from core.plugin_manager import PluginInstaller, PluginRegistry
        
        registry = PluginRegistry(temp_data_dir)
        installer = PluginInstaller(registry)
        
        # Create zip with invalid manifest (missing required fields)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("plugin.yaml", "description: missing name and version")
        
        result = installer.install(buffer.getvalue())
        
        assert result["success"] is False
        assert "error" in result

    def test_registers_plugin_after_install(self, temp_data_dir):
        """Test that installed plugin is registered in registry."""
        from core.plugin_manager import PluginInstaller, PluginRegistry
        
        registry = PluginRegistry(temp_data_dir)
        installer = PluginInstaller(registry)
        
        manifest = """
name: registered-plugin
version: 2.0.0
entry_point: my_plugin.tools
"""
        package_bytes = self._create_plugin_zip(manifest)
        
        installer.install(package_bytes)
        
        plugins = registry.list_plugins()
        assert len(plugins) == 1
        assert plugins[0]["name"] == "registered-plugin"
        assert plugins[0]["version"] == "2.0.0"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugin_manager.py::TestPluginInstaller -v`
Expected: FAIL with import error

**Step 3: Write minimal implementation**

```python
# Add to core/plugin_manager.py
import zipfile
import tarfile
import io
import shutil
import logging

logger = logging.getLogger(__name__)


class PluginInstaller:
    """Handles plugin package installation."""
    
    def __init__(self, registry: PluginRegistry):
        """Initialize the installer.
        
        Args:
            registry: Plugin registry instance
        """
        self.registry = registry
        self.installed_dir = registry.installed_dir
    
    def install(self, package_bytes: bytes, source: str = "upload") -> Dict[str, Any]:
        """Install a plugin from a zip/tar package.
        
        Args:
            package_bytes: Raw bytes of the package file
            source: Source of the package ("upload", "pypi", "git")
        
        Returns:
            Dict with success status and plugin info or error
        """
        try:
            # Try to open as zip first, then tar
            manifest, extracted_files = self._extract_package(package_bytes)
            
            if manifest is None:
                return {
                    "success": False,
                    "error": "Package does not contain a plugin.yaml manifest",
                }
            
            # Parse and validate manifest
            try:
                parsed_manifest = PluginManifest.from_yaml(manifest)
            except ValueError as e:
                return {
                    "success": False,
                    "error": f"Invalid manifest: {str(e)}",
                }
            
            plugin_name = parsed_manifest.name
            
            # Create plugin directory
            plugin_dir = self.installed_dir / plugin_name
            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True)
            
            # Write extracted files
            for file_path, content in extracted_files.items():
                full_path = plugin_dir / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                if isinstance(content, bytes):
                    full_path.write_bytes(content)
                else:
                    full_path.write_text(content)
            
            # Register in registry
            self.registry.register_plugin(
                name=plugin_name,
                version=parsed_manifest.version,
                source=source,
            )
            
            logger.info(f"Installed plugin: {plugin_name} v{parsed_manifest.version}")
            
            return {
                "success": True,
                "name": plugin_name,
                "version": parsed_manifest.version,
                "description": parsed_manifest.description,
                "config_required": [
                    name for name, field in parsed_manifest.config.items()
                    if field.required
                ],
            }
            
        except Exception as e:
            logger.error(f"Failed to install plugin: {e}")
            return {
                "success": False,
                "error": str(e),
            }
    
    def _extract_package(self, package_bytes: bytes) -> tuple:
        """Extract package contents.
        
        Returns:
            Tuple of (manifest_content, {path: content} dict)
        """
        manifest = None
        files = {}
        
        # Try zip first
        try:
            with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    content = zf.read(name)
                    
                    # Handle nested directory structure (plugin might be in subdirectory)
                    # Normalize path to remove leading directory if all files share one
                    files[name] = content
                    
                    if name == "plugin.yaml" or name.endswith("/plugin.yaml"):
                        manifest = content.decode("utf-8")
                
                return manifest, files
        except zipfile.BadZipFile:
            pass
        
        # Try tar
        try:
            with tarfile.open(fileobj=io.BytesIO(package_bytes), mode="r:*") as tf:
                for member in tf.getmembers():
                    if member.isfile():
                        f = tf.extractfile(member)
                        if f:
                            content = f.read()
                            files[member.name] = content
                            
                            if member.name == "plugin.yaml" or member.name.endswith("/plugin.yaml"):
                                manifest = content.decode("utf-8")
                
                return manifest, files
        except tarfile.TarError:
            pass
        
        raise ValueError("Package is not a valid zip or tar archive")
    
    def uninstall(self, plugin_name: str) -> Dict[str, Any]:
        """Uninstall a plugin.
        
        Args:
            plugin_name: Name of the plugin to uninstall
        
        Returns:
            Dict with success status
        """
        plugin_dir = self.installed_dir / plugin_name
        
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)
        
        self.registry.unregister_plugin(plugin_name)
        
        # Also remove config
        config_file = self.registry.config_dir / f"{plugin_name}.yaml"
        if config_file.exists():
            config_file.unlink()
        
        logger.info(f"Uninstalled plugin: {plugin_name}")
        
        return {"success": True, "name": plugin_name}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugin_manager.py::TestPluginInstaller -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/plugin_manager.py tests/test_plugin_manager.py
git commit -m "feat: add plugin installer for package extraction"
```

---

## Task 5: Create Plugin Loader Integration

**Files:**
- Modify: `core/plugin_manager.py`
- Test: `tests/test_plugin_manager.py`

**Step 1: Write the failing test for loading plugins**

```python
# Add to tests/test_plugin_manager.py

class TestPluginManager:
    """Tests for the main PluginManager class."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)

    def _create_plugin_zip(self, name: str, tool_code: str) -> bytes:
        """Helper to create a valid plugin zip file."""
        manifest = f"""
name: {name}
version: 1.0.0
entry_point: {name.replace('-', '_')}.tools
"""
        module_name = name.replace('-', '_')
        
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("plugin.yaml", manifest)
            zf.writestr(f"{module_name}/__init__.py", "")
            zf.writestr(f"{module_name}/tools.py", tool_code)
        return buffer.getvalue()

    def test_manager_loads_enabled_plugins(self, temp_data_dir):
        """Test that PluginManager loads tools from enabled plugins."""
        from core.plugin_manager import PluginManager
        
        manager = PluginManager(temp_data_dir)
        
        # Install a plugin
        tool_code = '''
from strands import tool

@tool
def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"
'''
        package = self._create_plugin_zip("greeting-plugin", tool_code)
        manager.install_plugin(package)
        
        # Load plugins
        tools = manager.load_plugins()
        
        assert len(tools) == 1
        # Tool should be callable
        assert callable(tools[0])

    def test_manager_skips_disabled_plugins(self, temp_data_dir):
        """Test that disabled plugins are not loaded."""
        from core.plugin_manager import PluginManager
        
        manager = PluginManager(temp_data_dir)
        
        tool_code = '''
from strands import tool

@tool
def disabled_tool() -> str:
    return "should not load"
'''
        package = self._create_plugin_zip("disabled-plugin", tool_code)
        manager.install_plugin(package)
        
        # Disable the plugin
        manager.disable_plugin("disabled-plugin")
        
        # Load plugins
        tools = manager.load_plugins()
        
        assert len(tools) == 0

    def test_manager_provides_config_to_plugins(self, temp_data_dir):
        """Test that plugins can access their configuration."""
        from core.plugin_manager import PluginManager
        
        manager = PluginManager(temp_data_dir)
        
        # Install plugin that reads config
        manifest = """
name: config-test
version: 1.0.0
entry_point: config_test.tools
config:
  greeting:
    type: string
    default: "Hello"
    label: "Greeting"
"""
        tool_code = '''
from strands import tool
from krell.plugins import get_config

@tool
def configured_greet(name: str) -> str:
    """Greet with configured greeting."""
    config = get_config()
    greeting = config.get("greeting", "Hi")
    return f"{greeting}, {name}!"
'''
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("plugin.yaml", manifest)
            zf.writestr("config_test/__init__.py", "")
            zf.writestr("config_test/tools.py", tool_code)
        
        manager.install_plugin(buffer.getvalue())
        
        # Set config
        manager.set_plugin_config("config-test", {"greeting": "Howdy"})
        
        # Verify config was saved
        config = manager.get_plugin_config("config-test")
        assert config["greeting"] == "Howdy"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugin_manager.py::TestPluginManager -v`
Expected: FAIL with import error

**Step 3: Write minimal implementation**

```python
# Add to core/plugin_manager.py
import importlib
import importlib.util
import sys


# Global config context for plugins
_current_plugin_config: Dict[str, Any] = {}


def get_config() -> Dict[str, Any]:
    """Get the current plugin's configuration.
    
    This is called by plugins to access their configuration values.
    """
    return dict(_current_plugin_config)


class PluginManager:
    """Main interface for plugin management.
    
    Combines registry, config storage, installer, and loader.
    """
    
    def __init__(self, data_dir: Path):
        """Initialize the plugin manager.
        
        Args:
            data_dir: Base data directory (e.g., ./data)
        """
        self.data_dir = Path(data_dir)
        self.registry = PluginRegistry(data_dir)
        self.config_storage = PluginConfigStorage(self.registry.config_dir)
        self.installer = PluginInstaller(self.registry)
        
        self._loaded_tools: List[Any] = []
        self._plugin_modules: Dict[str, Any] = {}
    
    def install_plugin(self, package_bytes: bytes, source: str = "upload") -> Dict[str, Any]:
        """Install a plugin from a package."""
        return self.installer.install(package_bytes, source)
    
    def uninstall_plugin(self, name: str) -> Dict[str, Any]:
        """Uninstall a plugin."""
        return self.installer.uninstall(name)
    
    def enable_plugin(self, name: str):
        """Enable a plugin."""
        self.registry.set_enabled(name, True)
    
    def disable_plugin(self, name: str):
        """Disable a plugin."""
        self.registry.set_enabled(name, False)
    
    def get_plugin_config(self, name: str) -> Dict[str, Any]:
        """Get a plugin's configuration."""
        return self.config_storage.load(name)
    
    def set_plugin_config(self, name: str, config: Dict[str, Any]):
        """Set a plugin's configuration."""
        # Load manifest to validate and apply defaults
        plugin_dir = self.registry.installed_dir / name
        manifest_path = plugin_dir / "plugin.yaml"
        
        if manifest_path.exists():
            manifest = PluginManifest.from_file(manifest_path)
            self.config_storage.validate_config(config, manifest)
            config = self.config_storage.apply_defaults(config, manifest)
        
        self.config_storage.save(name, config)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all installed plugins with their status."""
        result = []
        
        for plugin_info in self.registry.list_plugins():
            name = plugin_info["name"]
            plugin_dir = self.registry.installed_dir / name
            manifest_path = plugin_dir / "plugin.yaml"
            
            # Load manifest for additional info
            manifest = None
            if manifest_path.exists():
                try:
                    manifest = PluginManifest.from_file(manifest_path)
                except Exception:
                    pass
            
            # Check if configured
            config = self.config_storage.load(name)
            missing_config = []
            
            if manifest:
                for field_name, field_schema in manifest.config.items():
                    if field_schema.required and field_name not in config:
                        missing_config.append(field_name)
            
            result.append({
                **plugin_info,
                "description": manifest.description if manifest else "",
                "configured": len(missing_config) == 0,
                "missing_config": missing_config,
                "config_schema": {
                    name: {
                        "type": field.type,
                        "label": field.label,
                        "required": field.required,
                        "default": field.default,
                        "description": field.description,
                        "options": field.options,
                    }
                    for name, field in (manifest.config.items() if manifest else {})
                },
            })
        
        return result
    
    def get_plugin(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a specific plugin."""
        plugins = self.list_plugins()
        for plugin in plugins:
            if plugin["name"] == name:
                return plugin
        return None
    
    def load_plugins(self) -> List[Any]:
        """Load all enabled and configured plugins.
        
        Returns:
            List of tool functions from loaded plugins
        """
        global _current_plugin_config
        
        tools = []
        
        for plugin_info in self.list_plugins():
            name = plugin_info["name"]
            
            # Skip disabled plugins
            if not plugin_info["enabled"]:
                logger.debug(f"Skipping disabled plugin: {name}")
                continue
            
            # Skip unconfigured plugins (missing required config)
            if not plugin_info["configured"]:
                logger.warning(
                    f"Skipping plugin {name}: missing required config: "
                    f"{plugin_info['missing_config']}"
                )
                continue
            
            try:
                plugin_tools = self._load_plugin(name)
                tools.extend(plugin_tools)
                logger.info(f"Loaded {len(plugin_tools)} tools from plugin: {name}")
            except Exception as e:
                logger.error(f"Failed to load plugin {name}: {e}")
        
        self._loaded_tools = tools
        return tools
    
    def _load_plugin(self, name: str) -> List[Any]:
        """Load a single plugin's tools."""
        global _current_plugin_config
        
        plugin_dir = self.registry.installed_dir / name
        manifest_path = plugin_dir / "plugin.yaml"
        
        if not manifest_path.exists():
            raise ValueError(f"Plugin {name} has no manifest")
        
        manifest = PluginManifest.from_file(manifest_path)
        
        # Set up config context for this plugin
        config = self.config_storage.load(name)
        config = self.config_storage.apply_defaults(config, manifest)
        _current_plugin_config = config
        
        # Add plugin directory to sys.path temporarily
        plugin_dir_str = str(plugin_dir)
        if plugin_dir_str not in sys.path:
            sys.path.insert(0, plugin_dir_str)
        
        try:
            # Import the entry point module
            entry_point = manifest.entry_point
            
            # Clear any cached import
            if entry_point in sys.modules:
                del sys.modules[entry_point]
            
            module = importlib.import_module(entry_point)
            self._plugin_modules[name] = module
            
            # Find all @tool decorated functions
            tools = []
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if hasattr(attr, "__tool__") or (
                    callable(attr) and hasattr(attr, "__wrapped__")
                ):
                    tools.append(attr)
            
            return tools
            
        finally:
            # Clean up sys.path
            if plugin_dir_str in sys.path:
                sys.path.remove(plugin_dir_str)
    
    def get_tools(self) -> List[Any]:
        """Get currently loaded tools."""
        return self._loaded_tools
    
    def reload_plugins(self) -> List[Any]:
        """Reload all plugins."""
        # Clear module cache
        for name in list(self._plugin_modules.keys()):
            entry_point = None
            manifest_path = self.registry.installed_dir / name / "plugin.yaml"
            if manifest_path.exists():
                manifest = PluginManifest.from_file(manifest_path)
                entry_point = manifest.entry_point
            
            if entry_point and entry_point in sys.modules:
                del sys.modules[entry_point]
        
        self._plugin_modules.clear()
        return self.load_plugins()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugin_manager.py::TestPluginManager -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/plugin_manager.py tests/test_plugin_manager.py
git commit -m "feat: add PluginManager with full lifecycle management"
```

---

## Task 6: Add krell.plugins Module for get_config

**Files:**
- Create: `krell/__init__.py`
- Create: `krell/plugins.py`
- Test: `tests/test_plugin_manager.py` (add test)

**Step 1: Write the failing test**

```python
# Add to tests/test_plugin_manager.py

def test_krell_plugins_module_exports_get_config():
    """Test that krell.plugins module exports get_config function."""
    from krell.plugins import get_config
    
    assert callable(get_config)
    
    # Should return a dict (empty by default)
    result = get_config()
    assert isinstance(result, dict)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugin_manager.py::test_krell_plugins_module_exports_get_config -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Write minimal implementation**

```python
# krell/__init__.py
"""Krell plugin development utilities."""

# krell/plugins.py
"""Plugin utilities for Krell plugins.

This module provides utilities that plugins can use to access their configuration
and other Krell services.
"""

from core.plugin_manager import get_config

__all__ = ["get_config"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugin_manager.py::test_krell_plugins_module_exports_get_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add krell/__init__.py krell/plugins.py tests/test_plugin_manager.py
git commit -m "feat: add krell.plugins module for plugin utilities"
```

---

## Task 7: Add API Schemas for Plugins

**Files:**
- Modify: `api/schemas.py`
- Test: (API tests will be in Task 8)

**Step 1: Add schemas**

```python
# Add to api/schemas.py

class PluginConfigField(BaseModel):
    """Schema for a plugin configuration field."""
    type: str
    label: str
    required: bool = False
    default: Optional[Any] = None
    description: str = ""
    options: List[str] = []


class PluginInfo(BaseModel):
    """Information about an installed plugin."""
    name: str
    version: str
    description: str = ""
    enabled: bool
    configured: bool
    missing_config: List[str] = []
    config_schema: Dict[str, PluginConfigField] = {}
    source: str = "upload"
    installed_at: str = ""


class PluginListResponse(BaseModel):
    """Response for listing plugins."""
    plugins: List[PluginInfo]


class PluginConfigUpdateRequest(BaseModel):
    """Request to update plugin configuration."""
    config: Dict[str, Any]


class PluginUploadResponse(BaseModel):
    """Response after uploading a plugin."""
    success: bool
    name: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None
    config_required: List[str] = []
```

**Step 2: Commit**

```bash
git add api/schemas.py
git commit -m "feat: add API schemas for plugin management"
```

---

## Task 8: Add Plugin API Endpoints

**Files:**
- Modify: `api/routes.py`
- Test: `tests/test_api_endpoints.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_api_endpoints.py or create tests/test_plugin_api.py

import pytest
from fastapi.testclient import TestClient
import tempfile
import shutil
from pathlib import Path
import zipfile
import io


class TestPluginAPI:
    """Tests for plugin management API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client with temporary data directory."""
        # This would need setup to configure the app with temp directory
        from main import app
        return TestClient(app)

    def _create_plugin_zip(self, name: str) -> bytes:
        """Create a minimal valid plugin package."""
        manifest = f"""
name: {name}
version: 1.0.0
entry_point: {name.replace('-', '_')}.tools
"""
        tool_code = '''
from strands import tool

@tool  
def sample_tool() -> str:
    return "ok"
'''
        buffer = io.BytesIO()
        module_name = name.replace('-', '_')
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("plugin.yaml", manifest)
            zf.writestr(f"{module_name}/__init__.py", "")
            zf.writestr(f"{module_name}/tools.py", tool_code)
        return buffer.getvalue()

    def test_list_plugins_empty(self, client):
        """Test listing plugins when none installed."""
        response = client.get("/api/plugins")
        assert response.status_code == 200
        data = response.json()
        assert "plugins" in data
        assert isinstance(data["plugins"], list)

    def test_upload_plugin(self, client):
        """Test uploading a plugin package."""
        package = self._create_plugin_zip("test-plugin")
        
        response = client.post(
            "/api/plugins/upload",
            files={"file": ("test-plugin.zip", package, "application/zip")},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["name"] == "test-plugin"

    def test_get_plugin_details(self, client):
        """Test getting plugin details."""
        # First upload
        package = self._create_plugin_zip("detail-test")
        client.post(
            "/api/plugins/upload",
            files={"file": ("detail-test.zip", package, "application/zip")},
        )
        
        response = client.get("/api/plugins/detail-test")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "detail-test"

    def test_enable_disable_plugin(self, client):
        """Test enabling and disabling a plugin."""
        package = self._create_plugin_zip("toggle-test")
        client.post(
            "/api/plugins/upload",
            files={"file": ("toggle-test.zip", package, "application/zip")},
        )
        
        # Disable
        response = client.post("/api/plugins/toggle-test/disable")
        assert response.status_code == 200
        
        # Verify disabled
        response = client.get("/api/plugins/toggle-test")
        assert response.json()["enabled"] is False
        
        # Enable
        response = client.post("/api/plugins/toggle-test/enable")
        assert response.status_code == 200

    def test_update_plugin_config(self, client):
        """Test updating plugin configuration."""
        # Create plugin with config
        manifest = """
name: config-plugin
version: 1.0.0
entry_point: config_plugin.tools
config:
  api_key:
    type: secret
    required: true
    label: "API Key"
"""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("plugin.yaml", manifest)
            zf.writestr("config_plugin/__init__.py", "")
            zf.writestr("config_plugin/tools.py", "")
        
        client.post(
            "/api/plugins/upload",
            files={"file": ("config-plugin.zip", buffer.getvalue(), "application/zip")},
        )
        
        # Update config
        response = client.put(
            "/api/plugins/config-plugin/config",
            json={"config": {"api_key": "secret123"}},
        )
        assert response.status_code == 200

    def test_delete_plugin(self, client):
        """Test uninstalling a plugin."""
        package = self._create_plugin_zip("delete-test")
        client.post(
            "/api/plugins/upload",
            files={"file": ("delete-test.zip", package, "application/zip")},
        )
        
        response = client.delete("/api/plugins/delete-test")
        assert response.status_code == 200
        
        # Verify gone
        response = client.get("/api/plugins/delete-test")
        assert response.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_plugin_api.py -v`
Expected: FAIL (endpoints don't exist)

**Step 3: Write implementation**

```python
# Add to api/routes.py

from fastapi import UploadFile, File
from api.schemas import (
    PluginListResponse,
    PluginInfo,
    PluginConfigField,
    PluginConfigUpdateRequest,
    PluginUploadResponse,
)

# Initialize plugin manager (add near top of file after config)
from pathlib import Path
from core.plugin_manager import PluginManager

# Get data directory from config
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get or create the plugin manager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        data_dir = Path(config.database_path).parent
        _plugin_manager = PluginManager(data_dir)
    return _plugin_manager


@router.get("/plugins", response_model=PluginListResponse)
async def list_plugins():
    """List all installed plugins with their status."""
    manager = get_plugin_manager()
    plugins = manager.list_plugins()
    
    return PluginListResponse(
        plugins=[
            PluginInfo(
                name=p["name"],
                version=p["version"],
                description=p.get("description", ""),
                enabled=p["enabled"],
                configured=p["configured"],
                missing_config=p.get("missing_config", []),
                config_schema={
                    name: PluginConfigField(**field)
                    for name, field in p.get("config_schema", {}).items()
                },
                source=p.get("source", "upload"),
                installed_at=p.get("installed_at", ""),
            )
            for p in plugins
        ]
    )


@router.post("/plugins/upload", response_model=PluginUploadResponse)
async def upload_plugin(file: UploadFile = File(...)):
    """Upload and install a plugin package."""
    manager = get_plugin_manager()
    
    content = await file.read()
    result = manager.install_plugin(content)
    
    return PluginUploadResponse(
        success=result.get("success", False),
        name=result.get("name"),
        version=result.get("version"),
        error=result.get("error"),
        config_required=result.get("config_required", []),
    )


@router.get("/plugins/{plugin_name}")
async def get_plugin(plugin_name: str):
    """Get details about a specific plugin."""
    manager = get_plugin_manager()
    plugin = manager.get_plugin(plugin_name)
    
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    return PluginInfo(
        name=plugin["name"],
        version=plugin["version"],
        description=plugin.get("description", ""),
        enabled=plugin["enabled"],
        configured=plugin["configured"],
        missing_config=plugin.get("missing_config", []),
        config_schema={
            name: PluginConfigField(**field)
            for name, field in plugin.get("config_schema", {}).items()
        },
        source=plugin.get("source", "upload"),
        installed_at=plugin.get("installed_at", ""),
    )


@router.put("/plugins/{plugin_name}/config")
async def update_plugin_config(plugin_name: str, request: PluginConfigUpdateRequest):
    """Update a plugin's configuration."""
    manager = get_plugin_manager()
    
    plugin = manager.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    try:
        manager.set_plugin_config(plugin_name, request.config)
        return {"success": True, "message": "Configuration updated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/plugins/{plugin_name}/enable")
async def enable_plugin(plugin_name: str):
    """Enable a plugin."""
    manager = get_plugin_manager()
    
    plugin = manager.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    manager.enable_plugin(plugin_name)
    return {"success": True, "message": f"Plugin {plugin_name} enabled"}


@router.post("/plugins/{plugin_name}/disable")
async def disable_plugin(plugin_name: str):
    """Disable a plugin."""
    manager = get_plugin_manager()
    
    plugin = manager.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    manager.disable_plugin(plugin_name)
    return {"success": True, "message": f"Plugin {plugin_name} disabled"}


@router.delete("/plugins/{plugin_name}")
async def delete_plugin(plugin_name: str):
    """Uninstall a plugin."""
    manager = get_plugin_manager()
    
    plugin = manager.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    
    result = manager.uninstall_plugin(plugin_name)
    return {"success": True, "message": f"Plugin {plugin_name} uninstalled"}


@router.post("/plugins/reload")
async def reload_plugins():
    """Reload all plugins."""
    manager = get_plugin_manager()
    tools = manager.reload_plugins()
    
    return {
        "success": True,
        "message": "Plugins reloaded",
        "tools_count": len(tools),
    }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_plugin_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/routes.py api/schemas.py tests/test_plugin_api.py
git commit -m "feat: add plugin management API endpoints"
```

---

## Task 9: Update Dashboard UI for Plugin Management

**Files:**
- Modify: `templates/dashboard.html`

**Step 1: Add plugin management section to dashboard**

Replace the "Loaded Plugins" section with new plugin management UI:

```html
<!-- Plugin Management Section -->
<div class="bg-white rounded-lg shadow-md p-6 mb-6">
    <div class="flex justify-between items-center mb-4">
        <h2 class="text-2xl font-semibold">Plugin Management</h2>
        <div class="flex gap-2">
            <button onclick="document.getElementById('plugin-upload').click()"
                    class="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700">
                Upload Plugin
            </button>
            <input type="file" id="plugin-upload" accept=".zip,.tar.gz,.tgz" 
                   class="hidden" onchange="uploadPlugin(this.files[0])">
            <button hx-post="/api/plugins/reload" 
                    hx-target="#plugins-list"
                    hx-swap="innerHTML"
                    class="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700">
                Reload Plugins
            </button>
        </div>
    </div>
    
    <div id="upload-status" class="hidden mb-4 p-4 rounded"></div>
    
    <div id="plugins-list" 
         hx-get="/api/plugins" 
         hx-trigger="load"
         class="space-y-4">
        <p class="text-gray-600">Loading plugins...</p>
    </div>
</div>

<!-- Plugin Configuration Modal -->
<div id="config-modal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg shadow-xl p-6 w-full max-w-lg mx-4">
        <div class="flex justify-between items-center mb-4">
            <h3 class="text-xl font-semibold" id="config-modal-title">Configure Plugin</h3>
            <button onclick="closeConfigModal()" class="text-gray-500 hover:text-gray-700">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </div>
        <form id="config-form" class="space-y-4">
            <div id="config-fields"></div>
            <div class="flex gap-2 justify-end">
                <button type="button" onclick="closeConfigModal()"
                        class="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400">
                    Cancel
                </button>
                <button type="submit"
                        class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
                    Save Configuration
                </button>
            </div>
        </form>
    </div>
</div>
```

**Step 2: Add JavaScript for plugin management**

```html
<script>
// Plugin upload function
async function uploadPlugin(file) {
    const statusDiv = document.getElementById('upload-status');
    statusDiv.className = 'mb-4 p-4 rounded bg-blue-100 text-blue-800';
    statusDiv.textContent = 'Uploading plugin...';
    statusDiv.classList.remove('hidden');
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch('/api/plugins/upload', {
            method: 'POST',
            body: formData,
        });
        
        const data = await response.json();
        
        if (data.success) {
            statusDiv.className = 'mb-4 p-4 rounded bg-green-100 text-green-800';
            statusDiv.textContent = `Successfully installed ${data.name} v${data.version}`;
            
            if (data.config_required && data.config_required.length > 0) {
                statusDiv.textContent += `. Configuration required: ${data.config_required.join(', ')}`;
            }
            
            // Refresh plugin list
            htmx.trigger('#plugins-list', 'load');
        } else {
            statusDiv.className = 'mb-4 p-4 rounded bg-red-100 text-red-800';
            statusDiv.textContent = `Failed to install: ${data.error}`;
        }
    } catch (error) {
        statusDiv.className = 'mb-4 p-4 rounded bg-red-100 text-red-800';
        statusDiv.textContent = `Error: ${error.message}`;
    }
    
    // Hide after 5 seconds
    setTimeout(() => statusDiv.classList.add('hidden'), 5000);
    
    // Clear file input
    document.getElementById('plugin-upload').value = '';
}

// Toggle plugin enabled state
async function togglePlugin(name, enable) {
    const action = enable ? 'enable' : 'disable';
    try {
        await fetch(`/api/plugins/${name}/${action}`, { method: 'POST' });
        htmx.trigger('#plugins-list', 'load');
    } catch (error) {
        alert(`Failed to ${action} plugin: ${error.message}`);
    }
}

// Open configuration modal
let currentConfigPlugin = null;

async function openConfigModal(pluginName) {
    currentConfigPlugin = pluginName;
    
    try {
        const response = await fetch(`/api/plugins/${pluginName}`);
        const plugin = await response.json();
        
        document.getElementById('config-modal-title').textContent = `Configure ${plugin.name}`;
        
        // Build form fields
        const fieldsContainer = document.getElementById('config-fields');
        fieldsContainer.innerHTML = '';
        
        // Load current config
        const currentConfig = await loadPluginConfig(pluginName);
        
        for (const [fieldName, schema] of Object.entries(plugin.config_schema || {})) {
            const fieldDiv = document.createElement('div');
            
            const label = document.createElement('label');
            label.className = 'block text-sm font-medium text-gray-700 mb-1';
            label.textContent = schema.label + (schema.required ? ' *' : '');
            fieldDiv.appendChild(label);
            
            if (schema.description) {
                const desc = document.createElement('p');
                desc.className = 'text-xs text-gray-500 mb-1';
                desc.textContent = schema.description;
                fieldDiv.appendChild(desc);
            }
            
            let input;
            
            if (schema.type === 'choice') {
                input = document.createElement('select');
                input.className = 'w-full px-3 py-2 border border-gray-300 rounded-md';
                for (const option of schema.options) {
                    const opt = document.createElement('option');
                    opt.value = option;
                    opt.textContent = option;
                    input.appendChild(opt);
                }
            } else if (schema.type === 'bool') {
                input = document.createElement('input');
                input.type = 'checkbox';
                input.className = 'h-4 w-4 text-blue-600';
            } else if (schema.type === 'secret') {
                input = document.createElement('input');
                input.type = 'password';
                input.className = 'w-full px-3 py-2 border border-gray-300 rounded-md';
                input.placeholder = currentConfig[fieldName] ? '••••••••' : '';
            } else if (schema.type === 'int' || schema.type === 'float') {
                input = document.createElement('input');
                input.type = 'number';
                input.className = 'w-full px-3 py-2 border border-gray-300 rounded-md';
                if (schema.type === 'float') input.step = '0.01';
            } else {
                input = document.createElement('input');
                input.type = 'text';
                input.className = 'w-full px-3 py-2 border border-gray-300 rounded-md';
            }
            
            input.name = fieldName;
            input.id = `config-${fieldName}`;
            
            // Set current value
            if (schema.type === 'bool') {
                input.checked = currentConfig[fieldName] ?? schema.default ?? false;
            } else if (schema.type !== 'secret') {
                input.value = currentConfig[fieldName] ?? schema.default ?? '';
            }
            
            fieldDiv.appendChild(input);
            fieldsContainer.appendChild(fieldDiv);
        }
        
        document.getElementById('config-modal').classList.remove('hidden');
        
    } catch (error) {
        alert(`Failed to load plugin config: ${error.message}`);
    }
}

async function loadPluginConfig(pluginName) {
    try {
        const response = await fetch(`/api/plugins/${pluginName}`);
        const plugin = await response.json();
        // Config is stored separately, need to fetch it
        // For now return empty, actual config loading would need backend support
        return {};
    } catch {
        return {};
    }
}

function closeConfigModal() {
    document.getElementById('config-modal').classList.add('hidden');
    currentConfigPlugin = null;
}

// Handle config form submission
document.getElementById('config-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!currentConfigPlugin) return;
    
    const formData = new FormData(e.target);
    const config = {};
    
    for (const [key, value] of formData.entries()) {
        const input = document.getElementById(`config-${key}`);
        if (input.type === 'checkbox') {
            config[key] = input.checked;
        } else if (input.type === 'number') {
            config[key] = input.step === '0.01' ? parseFloat(value) : parseInt(value);
        } else if (value) {
            config[key] = value;
        }
    }
    
    try {
        const response = await fetch(`/api/plugins/${currentConfigPlugin}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ config }),
        });
        
        if (response.ok) {
            closeConfigModal();
            htmx.trigger('#plugins-list', 'load');
        } else {
            const data = await response.json();
            alert(`Failed to save: ${data.detail}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
});

// Delete plugin
async function deletePlugin(name) {
    if (!confirm(`Are you sure you want to uninstall ${name}?`)) return;
    
    try {
        await fetch(`/api/plugins/${name}`, { method: 'DELETE' });
        htmx.trigger('#plugins-list', 'load');
    } catch (error) {
        alert(`Failed to delete: ${error.message}`);
    }
}

// Update HTMX handler for plugins list
document.body.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id === 'plugins-list') {
        const data = JSON.parse(event.detail.xhr.response);
        
        if (data.plugins && data.plugins.length > 0) {
            let html = '';
            
            for (const plugin of data.plugins) {
                const statusColor = plugin.enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600';
                const configWarning = !plugin.configured ? 
                    '<span class="text-yellow-600 text-sm ml-2">⚠ Needs configuration</span>' : '';
                
                html += `
                    <div class="border rounded-lg p-4 flex items-center justify-between">
                        <div class="flex-1">
                            <div class="flex items-center gap-2">
                                <span class="font-semibold">${plugin.name}</span>
                                <span class="text-sm text-gray-500">v${plugin.version}</span>
                                <span class="px-2 py-1 text-xs rounded ${statusColor}">
                                    ${plugin.enabled ? 'Enabled' : 'Disabled'}
                                </span>
                                ${configWarning}
                            </div>
                            <p class="text-sm text-gray-600 mt-1">${plugin.description || 'No description'}</p>
                        </div>
                        <div class="flex gap-2">
                            <button onclick="openConfigModal('${plugin.name}')"
                                    class="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200">
                                Configure
                            </button>
                            <button onclick="togglePlugin('${plugin.name}', ${!plugin.enabled})"
                                    class="px-3 py-1 text-sm ${plugin.enabled ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700'} rounded hover:opacity-80">
                                ${plugin.enabled ? 'Disable' : 'Enable'}
                            </button>
                            <button onclick="deletePlugin('${plugin.name}')"
                                    class="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200">
                                Uninstall
                            </button>
                        </div>
                    </div>
                `;
            }
            
            event.detail.target.innerHTML = html;
        } else {
            event.detail.target.innerHTML = '<p class="text-gray-600">No plugins installed. Upload a plugin to get started.</p>';
        }
    }
});
</script>
```

**Step 2: Commit**

```bash
git add templates/dashboard.html
git commit -m "feat: add plugin management UI to dashboard"
```

---

## Task 10: Migrate Existing Plugins to New Format

**Files:**
- Create: `official-plugins/` directory with converted plugins
- Documentation for migration

**Step 1: Create official plugin packages**

This task involves converting the existing plugins in `plugins/` to the new package format. Each plugin becomes its own directory with `plugin.yaml`.

Example for weather plugin:

```
official-plugins/
└── weather-plugin/
    ├── plugin.yaml
    ├── pyproject.toml
    └── weather_plugin/
        ├── __init__.py
        └── tools.py
```

**plugin.yaml:**
```yaml
name: weather-plugin
version: 1.0.0
description: Get current weather and forecasts
author: Krell Team
entry_point: weather_plugin.tools

config:
  api_key:
    type: secret
    required: true
    label: "OpenWeather API Key"
    description: "Get one at openweathermap.org/api"
  
  default_units:
    type: choice
    options: ["imperial", "metric"]
    default: "imperial"
    label: "Temperature Units"

dependencies:
  - requests>=2.28.0
```

**Step 2: Create migration script**

```python
# scripts/migrate_plugins.py
"""Script to migrate old plugins to new format."""

import os
import shutil
from pathlib import Path

# This would be run once to convert existing plugins
# Implementation details would go here
```

**Step 3: Commit**

```bash
git add official-plugins/ scripts/migrate_plugins.py
git commit -m "feat: migrate existing plugins to new package format"
```

---

## Task 11: Integration with main.py

**Files:**
- Modify: `main.py`

**Step 1: Update main.py to use PluginManager**

```python
# In main.py, replace the old plugin loader with the new PluginManager

from core.plugin_manager import PluginManager

# Initialize plugin manager
plugin_manager = PluginManager(Path(config.database_path).parent)

# Load plugins on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    await db.init_db()
    
    # Load plugins using new manager
    tools = plugin_manager.load_plugins()
    logger.info(f"Loaded {len(tools)} tools from plugins")
    
    yield
    
    logger.info("Shutting down...")
```

**Step 2: Update plugin-related dashboard endpoints**

Replace the old dashboard plugin endpoints to use the new PluginManager.

**Step 3: Commit**

```bash
git add main.py
git commit -m "feat: integrate PluginManager into main application"
```

---

## Task 12: Add Documentation

**Files:**
- Update: `docs/PLUGINS.md`

**Step 1: Update plugin documentation**

Add comprehensive documentation for:
- Creating plugins
- Plugin manifest format
- Configuration schema
- Installing plugins
- Dashboard usage

**Step 2: Commit**

```bash
git add docs/PLUGINS.md
git commit -m "docs: update plugin documentation for new system"
```

---

## Summary

This plan implements the full plugin management system in 12 tasks:

1. **Plugin Manifest Schema** - Parse and validate plugin.yaml
2. **Plugin Registry** - Track installed plugins
3. **Plugin Config Storage** - Store and validate configuration
4. **Plugin Installer** - Extract and install packages
5. **Plugin Manager** - Main interface combining all components
6. **krell.plugins Module** - Expose get_config() to plugins
7. **API Schemas** - Pydantic models for API
8. **API Endpoints** - REST endpoints for management
9. **Dashboard UI** - Web interface for management
10. **Migrate Plugins** - Convert existing plugins
11. **Integration** - Wire into main.py
12. **Documentation** - Update docs

Each task follows TDD with clear test-first development and frequent commits.
