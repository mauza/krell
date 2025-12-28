# core/plugin_manager.py
"""
Plugin manager for Krell's runtime plugin system.

Handles plugin installation, configuration, and lifecycle management.
"""

import yaml
import zipfile
import tarfile
import io
import shutil
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, field
from pathlib import Path


logger = logging.getLogger(__name__)


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
                elif field_schema.type == "float" and not isinstance(
                    value, (int, float)
                ):
                    raise ValueError(f"Config field '{field_name}' must be a number")
                elif field_schema.type == "bool" and not isinstance(value, bool):
                    raise ValueError(f"Config field '{field_name}' must be a boolean")
                elif (
                    field_schema.type == "choice" and value not in field_schema.options
                ):
                    raise ValueError(
                        f"Config field '{field_name}' must be one of: {field_schema.options}"
                    )

    def apply_defaults(
        self, config: Dict[str, Any], manifest: PluginManifest
    ) -> Dict[str, Any]:
        """Apply default values for missing optional fields."""
        result = dict(config)

        for field_name, field_schema in manifest.config.items():
            if field_name not in result and field_schema.default is not None:
                result[field_name] = field_schema.default

        return result


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
                    name
                    for name, field in parsed_manifest.config.items()
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

                            if member.name == "plugin.yaml" or member.name.endswith(
                                "/plugin.yaml"
                            ):
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
