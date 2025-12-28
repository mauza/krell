# core/plugin_manager.py
"""
Plugin manager for Krell's runtime plugin system.

Handles plugin installation, configuration, and lifecycle management.
"""

import yaml
from datetime import datetime, timezone
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

        self._plugins: Dict[str, PluginRegistryEntry] = {}
        self._ensure_directories()
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
            installed_at=datetime.now(timezone.utc).isoformat(),
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
