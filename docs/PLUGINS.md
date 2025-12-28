# Plugin System

Krell uses a plugin system for extending the agent's capabilities. This document covers both the **runtime plugin system** for installing plugins without rebuilding Docker, and **development guidance** for creating new plugins.

## Table of Contents

- [Overview](#overview)
- [Installing Plugins](#installing-plugins)
- [Plugin Package Structure](#plugin-package-structure)
- [Configuration Schema](#configuration-schema)
- [Creating Plugins](#creating-plugins)
- [Built-in Plugins](#built-in-plugins)
- [API Endpoints](#api-endpoints)
- [Dashboard Usage](#dashboard-usage)
- [Troubleshooting](#troubleshooting)

---

## Overview

Krell's plugin system allows you to:

1. **Install plugins at runtime** - Upload plugin packages via the dashboard without rebuilding Docker
2. **Configure plugins** - Set API keys and options through the dashboard UI
3. **Enable/disable plugins** - Toggle plugins on and off without uninstalling
4. **Hot-reload** - Reload plugins without restarting the server

### How It Works

- Plugins are stored in `data/plugins/installed/`
- Each plugin has a `plugin.yaml` manifest defining its metadata and configuration schema
- Plugin configuration is stored in `data/plugins/config/`
- A registry file (`data/plugins/registry.yaml`) tracks installed plugins and their state

---

## Installing Plugins

### Via Dashboard (Recommended)

1. Go to the dashboard at `http://localhost:8000/dashboard`
2. Find the "Plugin Management" section
3. Click "Upload Plugin"
4. Select a plugin package (`.zip` or `.tar.gz`)
5. Configure any required settings when prompted
6. Click "Enable" to activate the plugin

### Via API

```bash
# Upload a plugin package
curl -X POST http://localhost:8000/api/plugins/upload \
  -F "file=@my-plugin.zip"

# Configure the plugin
curl -X PUT http://localhost:8000/api/plugins/my-plugin/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"api_key": "your-secret-key"}}'

# Enable the plugin
curl -X POST http://localhost:8000/api/plugins/my-plugin/enable
```

### No Docker Rebuild Required

Plugins are installed to `data/plugins/` which is typically mounted as a Docker volume. This means:

- Plugins persist across container restarts
- No image rebuild needed to add plugins
- Configuration is preserved when updating containers

---

## Plugin Package Structure

A plugin package is a zip or tar.gz file with the following structure:

```
my-plugin/
├── plugin.yaml          # Required: Plugin manifest
├── my_plugin/           # Python package matching entry_point
│   ├── __init__.py
│   └── tools.py         # Contains @tool decorated functions
├── requirements.txt     # Optional: Python dependencies
└── README.md            # Optional: Documentation
```

### plugin.yaml Manifest

The manifest file defines plugin metadata and configuration:

```yaml
# Required fields
name: weather-plugin          # Unique plugin identifier (kebab-case)
version: 1.0.0               # Semantic version
entry_point: weather_plugin.tools  # Python module path to load

# Optional fields
description: Get weather forecasts and current conditions
author: Your Name

# Configuration schema (optional)
config:
  api_key:
    type: secret
    required: true
    label: "API Key"
    description: "Your OpenWeatherMap API key"
  
  units:
    type: choice
    options: ["imperial", "metric"]
    default: "imperial"
    label: "Temperature Units"
    description: "Display temperatures in Fahrenheit or Celsius"

# Python dependencies (optional)
dependencies:
  - requests>=2.28.0
```

---

## Configuration Schema

Plugin configuration fields support these types:

| Type | Description | Example |
|------|-------------|---------|
| `string` | Text input | `{ type: string, default: "hello" }` |
| `secret` | Password/API key (masked in UI) | `{ type: secret, required: true }` |
| `bool` | True/false toggle | `{ type: bool, default: true }` |
| `int` | Integer number | `{ type: int, default: 10 }` |
| `float` | Decimal number | `{ type: float, default: 0.5 }` |
| `choice` | Dropdown selection | `{ type: choice, options: ["a", "b"] }` |
| `list` | Array of values | `{ type: list, default: [] }` |

### Field Properties

```yaml
config:
  my_field:
    type: string        # Required: field type
    label: "My Field"   # Required: display label in UI
    required: false     # Is this field required? (default: false)
    default: "value"    # Default value if not set
    description: ""     # Help text shown in UI
    options: []         # For 'choice' type: available options
```

### Accessing Configuration in Plugins

Use `get_config()` to access your plugin's configuration:

```python
from krell.plugins import get_config

@tool
def my_tool() -> dict:
    """A tool that uses configuration."""
    config = get_config()
    
    api_key = config.get("api_key")
    units = config.get("units", "imperial")
    
    # Use configuration values...
    return {"status": "ok"}
```

---

## Creating Plugins

### Quick Start

1. Create a directory for your plugin:

```bash
mkdir my-awesome-plugin
cd my-awesome-plugin
```

2. Create the plugin manifest (`plugin.yaml`):

```yaml
name: my-awesome-plugin
version: 1.0.0
description: Does something awesome
entry_point: my_awesome_plugin.tools
```

3. Create the Python package:

```bash
mkdir my_awesome_plugin
touch my_awesome_plugin/__init__.py
```

4. Create your tools (`my_awesome_plugin/tools.py`):

```python
from strands import tool

@tool
def do_awesome_thing(input: str) -> dict:
    """
    Do something awesome with the input.
    
    The LLM reads this docstring to decide when to use the tool.
    
    Args:
        input: The thing to make awesome
        
    Returns:
        Dictionary with the awesome result
    """
    result = input.upper() + "!!!"
    return {"awesome_result": result}
```

5. Package it:

```bash
cd ..
zip -r my-awesome-plugin.zip my-awesome-plugin/
```

6. Upload via dashboard or API

### Example: Plugin with Configuration

```yaml
# plugin.yaml
name: stock-tracker
version: 1.0.0
description: Get real-time stock prices
entry_point: stock_tracker.tools

config:
  api_key:
    type: secret
    required: true
    label: "Alpha Vantage API Key"
    description: "Get a free key at alphavantage.co"
  
  default_currency:
    type: choice
    options: ["USD", "EUR", "GBP"]
    default: "USD"
    label: "Display Currency"
```

```python
# stock_tracker/tools.py
from strands import tool
from krell.plugins import get_config
import requests

@tool
def get_stock_price(symbol: str) -> dict:
    """
    Get the current price for a stock symbol.
    
    Args:
        symbol: Stock ticker symbol (e.g., "AAPL", "GOOGL")
        
    Returns:
        Current price and daily change
    """
    config = get_config()
    api_key = config.get("api_key")
    
    if not api_key:
        return {"error": "API key not configured"}
    
    try:
        response = requests.get(
            "https://api.example.com/stock",
            params={"symbol": symbol, "apikey": api_key},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        return {
            "symbol": symbol,
            "price": data["price"],
            "change": data["change"],
            "currency": config.get("default_currency", "USD")
        }
    except requests.RequestException as e:
        return {"error": f"Failed to fetch: {str(e)}"}
```

### Best Practices

#### Docstrings

Write clear docstrings - the LLM uses them to decide when to use your tool:

```python
@tool
def send_notification(message: str, urgency: str = "normal") -> dict:
    """
    Send a notification to the user's device.
    
    Use this tool when:
    - The user explicitly asks to be reminded or notified
    - An important event or deadline is approaching
    
    Do NOT use this tool for:
    - Regular conversation responses
    - Confirming routine actions
    
    Args:
        message: The notification content (keep under 100 characters)
        urgency: Priority level - "low", "normal", or "high"
        
    Returns:
        Success status and notification ID
    """
```

#### Type Hints

Always use type hints:

```python
# Good
@tool
def search(query: str, limit: int = 10) -> dict:
    ...

# Bad - no types
@tool
def search(query, limit=10):
    ...
```

#### Return Values

Return structured dictionaries:

```python
# Good
return {
    "success": True,
    "items": [...],
    "count": 42,
    "message": "Found 42 items"
}

# Bad
return "Found 42 items"
```

#### Error Handling

Handle errors gracefully:

```python
@tool
def fetch_data(url: str) -> dict:
    """Fetch data from a URL."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except requests.Timeout:
        return {"error": "Request timed out. Try again later."}
    except requests.RequestException as e:
        return {"error": f"Failed to fetch data: {str(e)}"}
```

---

## Built-in Plugins

Krell includes these plugins in the `plugins/` directory:

| Plugin | Tools | Description |
|--------|-------|-------------|
| `entity_tool.py` | `create_entity`, `update_entity`, `search_entities` | Manage people, places, things |
| `event_tool.py` | `create_event`, `update_event`, `search_events` | Track events and gatherings |
| `journal_tool.py` | `create_journal`, `search_journals` | Diary entries and reflections |
| `rating_tool.py` | `create_rating`, `get_ratings`, `get_rating_stats` | Rate entities and events |
| `conversation_tool.py` | `search_past_conversations` | Search conversation history |
| `datetime_tool.py` | `get_current_datetime` | Get current date/time |
| `weather_tool.py` | `get_weather` | Weather information |

These are loaded from the `plugins/` directory at startup and are separate from the runtime plugin system.

---

## API Endpoints

### List Plugins

```http
GET /api/plugins
```

Returns all installed plugins with status and configuration.

### Upload Plugin

```http
POST /api/plugins/upload
Content-Type: multipart/form-data

file: <plugin.zip>
```

### Get Plugin Details

```http
GET /api/plugins/{plugin_name}
```

### Update Configuration

```http
PUT /api/plugins/{plugin_name}/config
Content-Type: application/json

{
  "config": {
    "api_key": "secret123",
    "units": "metric"
  }
}
```

### Enable/Disable

```http
POST /api/plugins/{plugin_name}/enable
POST /api/plugins/{plugin_name}/disable
```

### Uninstall

```http
DELETE /api/plugins/{plugin_name}
```

### Reload All Plugins

```http
POST /api/plugins/reload
```

---

## Dashboard Usage

The dashboard at `http://localhost:8000/dashboard` provides a UI for plugin management:

### Plugin List

Shows all installed plugins with:
- Name and version
- Enabled/disabled status
- Configuration status (shows warning if required config missing)

### Actions

- **Configure**: Opens a form to set plugin configuration values
- **Enable/Disable**: Toggle plugin active state
- **Uninstall**: Remove the plugin completely

### Upload

Click "Upload Plugin" to install a new plugin from a `.zip` or `.tar.gz` file.

### Reload

Click "Reload Plugins" to reload all plugins without restarting the server.

---

## Troubleshooting

### Plugin Not Loading

1. Check the manifest:
   ```bash
   # Verify plugin.yaml is valid
   python -c "import yaml; yaml.safe_load(open('plugin.yaml'))"
   ```

2. Check entry point matches module path:
   - `entry_point: my_plugin.tools` requires `my_plugin/tools.py`

3. Check server logs for import errors

### Configuration Issues

- Ensure required fields are set before enabling
- Check field types match expected values (e.g., int vs string)
- Secret fields show as masked but are stored in plain text in config files

### Tool Not Being Called

- Review the docstring - is it clear when to use the tool?
- Test with explicit prompts: "Use the X tool to..."
- Check parameter types are appropriate

### Plugin Files Location

```
data/
└── plugins/
    ├── installed/          # Extracted plugin packages
    │   └── my-plugin/
    │       ├── plugin.yaml
    │       └── my_plugin/
    ├── config/             # Plugin configuration files
    │   └── my-plugin.yaml
    └── registry.yaml       # Plugin registry (enabled state, etc.)
```
