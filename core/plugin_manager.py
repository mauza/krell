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
