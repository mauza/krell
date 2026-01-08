# Krell

A self-hosted agentic AI backend for building personal AI assistants. Krell provides tool calling, persistent memory, entity tracking, and low-latency text-to-speech — all running on your own infrastructure.

Built on [Strands Agents](https://github.com/strands-agents/sdk-python) with a hot-reloadable plugin system.

## Features

- **Agentic AI** — LLM-powered assistant with autonomous tool calling
- **Entity System** — Track people, places, things, events, and experiences
- **Persistent Memory** — SQLite-backed conversation history and journal entries
- **Plugin System** — Hot-reloadable tools with zero-restart deployment
- **Text-to-Speech** — Low-latency streaming TTS with Kyutai
- **Web Dashboard** — Monitor status, configure settings, view activity
- **OpenAI-Compatible** — Works with OpenAI, Ollama, and any compatible API

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/krell.git
cd krell

# Install dependencies
uv sync

# Run the server
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

### Configure Your LLM

Krell works with any OpenAI-compatible API. Choose one:

**Option A: OpenAI**
```bash
export OPENAI_API_KEY="your-api-key"
```

**Option B: Ollama (Local)**
```bash
# Install Ollama: https://ollama.ai
ollama pull llama3.1:8b
```
Then update `config.yaml`:
```yaml
llm:
  endpoint: "http://localhost:11434"
  model: "llama3.1:8b"
```

### Access the App

| URL | Description |
|-----|-------------|
| http://localhost:8000 | API root |
| http://localhost:8000/docs | Interactive API docs (Swagger) |
| http://localhost:8000/dashboard | Web dashboard |

## Project Structure

```
krell/
├── api/                  # FastAPI routes and WebSocket handlers
├── core/                 # Agent and plugin loader
├── database/             # SQLite database and migrations
├── docs/                 # Documentation
├── plugins/              # Tool plugins (hot-reloadable)
├── services/             # TTS and LLM services
├── templates/            # Dashboard HTML templates
├── tests/                # Test suite
├── config.yaml           # Configuration file
└── main.py               # Application entry point
```

## Configuration

Krell uses `config.yaml` for configuration. Key settings:

```yaml
# LLM Configuration
llm:
  model: "gpt-4o-mini"
  endpoint: "https://api.openai.com"
  openai_api_key: ""  # Or use OPENAI_API_KEY env var

# Database
database:
  path: "./data/krell.db"

# Server
server:
  host: "0.0.0.0"
  port: 8000
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for full configuration reference.

## Plugins

Krell includes several built-in tools:

| Plugin | Description |
|--------|-------------|
| `entity_tool` | Create and manage entities (people, places, things) |
| `event_tool` | Track events with participants and locations |
| `journal_tool` | Create and search journal entries |
| `rating_tool` | Rate entities and events (1-5 scale) |
| `conversation_tool` | Search past conversations |
| `datetime_tool` | Get current date/time |
| `weather_tool` | Get weather information |

### Creating Custom Plugins

Add a new file to `plugins/`:

```python
from strands import tool

@tool
def my_custom_tool(query: str) -> str:
    """
    Description of what this tool does.
    The LLM sees this docstring to decide when to use the tool.
    
    Args:
        query: What to search for
        
    Returns:
        The search results
    """
    # Your logic here
    return f"Results for: {query}"
```

Plugins are automatically discovered and hot-reloaded — no server restart needed.

See [docs/PLUGINS.md](docs/PLUGINS.md) for the complete plugin development guide.

## API Reference

### Chat

```bash
# Send a message
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!", "conversation_id": null}'
```

### Conversations

```bash
# List conversations
curl http://localhost:8000/api/conversations

# Get conversation with messages
curl http://localhost:8000/api/conversations/{id}

# Delete conversation
curl -X DELETE http://localhost:8000/api/conversations/{id}
```

### Entities

```bash
# List entities
curl http://localhost:8000/api/entities

# Create entity
curl -X POST http://localhost:8000/api/entities \
  -H "Content-Type: application/json" \
  -d '{"type": "person", "name": "John", "description": "Friend from work"}'
```

See [docs/API.md](docs/API.md) for the complete API reference.

## Database

Krell uses SQLite with the following schema:

- **conversations** — Chat sessions with titles
- **messages** — Individual messages with role and tool calls
- **entities** — People, places, and things
- **events** — Meetings, gatherings, experiences
- **journals** — Reflections and diary entries
- **ratings** — 1-5 scores for entities and events
- **settings** — Runtime configuration (API keys encrypted)

### Migrations

Run database migrations:

```bash
make migrate
```

Or manually:

```bash
uv run python -m database.migrate ./data/krell.db
```

## Development

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_api_endpoints.py -v

# Run with coverage
uv run pytest tests/ --cov=. --cov-report=html
```

### Makefile Commands

```bash
make build      # Build Docker image
make run        # Build and run locally
make migrate    # Run database migrations
make help       # Show all commands
```

## Docker

```bash
# Build
docker build -t krell .

# Run
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -e OPENAI_API_KEY="your-key" \
  krell
```

### Docker Compose

```yaml
version: '3.8'
services:
  krell:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./plugins:/app/plugins
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
```

## Production Deployment

### Recommended Stack

- **Reverse Proxy** — Nginx or Caddy for HTTPS
- **Process Manager** — systemd or Docker
- **Database Backups** — Automated SQLite backups

### Security Considerations

- The dashboard has **no authentication** by default — add auth or firewall it
- API keys are encrypted at rest using Fernet
- Use HTTPS in production via reverse proxy
- Restrict network access to trusted clients

### Example systemd Service

```ini
[Unit]
Description=Krell AI Backend
After=network.target

[Service]
Type=simple
User=krell
WorkingDirectory=/opt/krell
ExecStart=/opt/krell/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
Environment="OPENAI_API_KEY=your-key"

[Install]
WantedBy=multi-user.target
```

## Troubleshooting

### TTS Errors on Apple Silicon (MPS)

If you see errors like `The operator 'aten::index_copy.out' is not currently implemented for the MPS device`:

**Solution**: The `start.sh` script now automatically sets `PYTORCH_ENABLE_MPS_FALLBACK=1`. If running manually:

```bash
export PYTORCH_ENABLE_MPS_FALLBACK=1
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

This enables CPU fallback for PyTorch operations not yet implemented on Apple's Metal GPU.

### LLM Connection Errors

If you see `No models loaded` errors:

1. **LM Studio**: Ensure a model is loaded in the LM Studio UI
2. **Ollama**: Run `ollama list` to verify models are available
3. **OpenAI**: Check your API key is set correctly

The error message will now indicate the specific issue (no model loaded vs. connection failed).

## Documentation

- [Configuration Guide](docs/CONFIGURATION.md) — Full configuration reference
- [Plugin Development](docs/PLUGINS.md) — Creating custom tools
- [API Reference](docs/API.md) — Complete API documentation
- [Entity System](docs/ENTITY_SYSTEM.md) — How entity tracking works

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Links

- [Strands Agents SDK](https://github.com/strands-agents/sdk-python)
- [Kyutai TTS](https://huggingface.co/kyutai/tts-1.6b-en_fr)
- [Ollama](https://ollama.ai)
- [FastAPI](https://fastapi.tiangolo.com)
