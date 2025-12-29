# Plugin System Design

> Runtime plugin management for Krell - install, configure, and manage plugins without rebuilding containers.

## Goals

- **Decouple deployment from plugin management** - Add/remove plugins without rebuilding Docker containers
- **Support multiple user types** - Developers can build plugins, non-technical users can install and configure them
- **Dashboard-driven configuration** - All plugin settings manageable through the web UI
- **Standard packaging** - Use Python packaging conventions for consistency and validation

## Plugin Package Structure

A Krell plugin is a standard Python package with an added manifest:

```
my-weather-plugin/
├── plugin.yaml          # Required: Plugin metadata & config schema
├── pyproject.toml       # Standard Python packaging
├── my_weather_plugin/
│   ├── __init__.py
│   └── tools.py         # Contains @tool decorated functions
└── README.md
```

### plugin.yaml Manifest

```yaml
name: weather-plugin
version: 1.0.0
description: Get weather forecasts
author: Your Name

# Entry point - module containing @tool functions
entry_point: my_weather_plugin.tools

# Configuration schema (shown in dashboard)
config:
  api_key:
    type: secret
    required: true
    label: "OpenWeather API Key"
    description: "Get one at openweathermap.org"
  
  default_units:
    type: choice
    options: ["imperial", "metric"]
    default: "imperial"
    label: "Temperature Units"
  
  cache_duration:
    type: int
    default: 300
    label: "Cache Duration (seconds)"
  
  enable_alerts:
    type: bool
    default: true
    label: "Show Weather Alerts"

# Optional: Python dependencies beyond Krell's base
dependencies:
  - requests>=2.28.0
```

### Configuration Types

| Type | Dashboard UI | Example Use |
|------|--------------|-------------|
| `string` | Text input | API endpoints, usernames |
| `secret` | Password input (masked) | API keys, tokens |
| `bool` | Toggle switch | Enable/disable features |
| `int` | Number input (whole) | Retry counts, limits |
| `float` | Number input (decimal) | Timeouts, thresholds |
| `choice` | Dropdown select | Units, modes |
| `list` | Multi-select or tag input | Allowed values, categories |

## Runtime Storage

Plugins are stored in a persistent volume that survives container rebuilds:

```
data/
├── plugins/
│   ├── installed/           # Extracted plugin packages
│   │   ├── weather-plugin/
│   │   └── calendar-plugin/
│   ├── config/              # User configuration per plugin
│   │   ├── weather-plugin.yaml
│   │   └── calendar-plugin.yaml
│   └── registry.yaml        # Tracks installed plugins & state
```

### registry.yaml

Tracks all installed plugins and their state:

```yaml
plugins:
  weather-plugin:
    version: 1.0.0
    installed_at: 2025-01-15T10:30:00Z
    enabled: true
    source: upload          # or "pypi", "git" later
  
  calendar-plugin:
    version: 2.1.0
    installed_at: 2025-01-14T08:00:00Z
    enabled: false          # Disabled but still installed
    source: upload
```

### Key Behaviors

- Plugins installed to a **persistent volume** (survives container rebuilds)
- Each plugin's config stored separately (easy to backup/restore)
- Plugins can be **enabled/disabled** without uninstalling
- Plugin loader reads from `data/plugins/` instead of bundled `plugins/`

## Plugin Loader

The plugin loader will:

1. **Read the registry** - Check which plugins are installed and enabled
2. **Validate configs** - Ensure required config values are set
3. **Install dependencies** - Run `pip install` for plugin dependencies if needed
4. **Load entry points** - Import the module specified in `plugin.yaml`
5. **Inject configuration** - Make config values available to the plugin

### Accessing Configuration in Plugins

Plugins access their configuration via a `get_config()` function:

```python
from strands import tool
from krell.plugins import get_config

@tool
def get_weather(location: str) -> dict:
    """Get weather for a location."""
    config = get_config()  # Gets this plugin's config
    api_key = config["api_key"]
    units = config.get("default_units", "imperial")
    # ... rest of implementation
```

## Existing Plugins Migration

All current bundled plugins will be converted to the new format:

- `weather_tool.py` -> `weather-plugin/`
- `journal_tool.py` -> `journal-plugin/`
- `entity_tool.py` -> `entity-plugin/`
- `event_tool.py` -> `event-plugin/`
- `datetime_tool.py` -> `datetime-plugin/`
- `rating_tool.py` -> `rating-plugin/`
- `conversation_tool.py` -> `conversation-plugin/`

These become "official" plugins that users can enable/disable like any other plugin.

## Dashboard Integration

### Plugins List Page

- Shows all installed plugins with status (enabled/disabled/needs config)
- Toggle to enable/disable each plugin
- "Configure" button for plugins with settings
- "Uninstall" button
- "Upload Plugin" button at the top

### Plugin Configuration Modal/Page

- Renders form fields based on `plugin.yaml` config schema
- Shows labels, descriptions, validation errors
- "Save" persists to `data/plugins/config/{plugin-name}.yaml`
- Visual indicator for required fields not yet set

### Plugin Upload Flow

1. User clicks "Upload Plugin"
2. Selects `.zip` or `.tar.gz` file
3. System validates:
   - Contains valid `plugin.yaml`
   - Has required fields (name, version, entry_point)
   - No conflicting plugin name already installed
4. Extracts to `data/plugins/installed/{name}/`
5. If plugin has required config, prompts user to configure before enabling

### Wireframe

```
┌─────────────────────────────────────────────────────┐
│ Plugins                          [Upload Plugin]    │
├─────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────┐ │
│ │ ☑ weather-plugin v1.0.0                         │ │
│ │   Get weather forecasts            [Configure]  │ │
│ └─────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────┐ │
│ │ ☐ calendar-plugin v2.1.0         ⚠ Needs config │ │
│ │   Manage calendar events           [Configure]  │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/plugins` | List all installed plugins with status |
| `POST` | `/api/plugins/upload` | Upload and install a plugin package |
| `GET` | `/api/plugins/{name}` | Get plugin details and config schema |
| `PUT` | `/api/plugins/{name}/config` | Save plugin configuration |
| `POST` | `/api/plugins/{name}/enable` | Enable a plugin |
| `POST` | `/api/plugins/{name}/disable` | Disable a plugin |
| `DELETE` | `/api/plugins/{name}` | Uninstall a plugin |
| `POST` | `/api/plugins/reload` | Reload all plugins (pick up changes) |

### Response Examples

**GET /api/plugins**

```json
{
  "plugins": [
    {
      "name": "weather-plugin",
      "version": "1.0.0",
      "description": "Get weather forecasts",
      "enabled": true,
      "configured": true,
      "tools": ["get_weather"]
    },
    {
      "name": "calendar-plugin", 
      "version": "2.1.0",
      "description": "Manage calendar events",
      "enabled": false,
      "configured": false,
      "missing_config": ["api_key", "calendar_id"]
    }
  ]
}
```

## Future Enhancements

These are out of scope for the initial implementation but could be added later:

- **PyPI installation** - Install plugins directly from PyPI (`pip install krell-weather-plugin`)
- **Git URL installation** - Install from GitHub/GitLab repositories
- **Plugin marketplace** - Curated registry of community plugins
- **Plugin updates** - Check for and install newer versions
- **Plugin sandboxing** - Security isolation for untrusted plugins
