# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and Run Commands

```bash
# Install dependencies
uv sync

# Run the server
uv run uvicorn main:app --host 0.0.0.0 --port 8000

# Run all tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_api_endpoints.py -v

# Run a single test
uv run pytest tests/test_api_endpoints.py::test_list_conversations_returns_list -v

# Run database migrations
make migrate
# or: uv run python -m database.migrate

# Docker build
make build
```

## Architecture Overview

Krell is a self-hosted agentic AI backend built on FastAPI and Strands Agents. Key architectural components:

### Entry Point and Startup (`main.py`)
- FastAPI app with lifespan management for startup/shutdown
- Initializes database, loads Kyutai TTS model eagerly, loads plugins
- Built-in plugins loaded via `PluginLoader`, runtime plugins via `PluginManager`

### Core Components (`core/`)
- **agent.py**: Wraps Strands Agent with OpenAI-compatible LLM backend. Context limit management (default 20 messages). Tools injected via `agent._strands_agent.tools`.
- **plugin_loader.py**: Discovers `@tool` decorated functions from `plugins/` directory. Supports hot-reload.
- **plugin_manager.py**: Runtime plugin system for user-installed plugins with manifest support (`plugin.yaml`).

### API Layer (`api/`)
- **routes.py**: REST endpoints for conversations, plugins, TTS streaming, health checks. Agent instance cached with async lock.
- **websocket.py**: Real-time bidirectional chat at `/api/ws/chat`. Streams text chunks, audio, tool calls/results.

### Services (`services/`)
- **tts.py** and **kyutai_model.py**: In-process Kyutai TTS with PyTorch inference. Supports CUDA, MPS (Apple), XPU (Intel), CPU.
- **tts_streaming.py**: Coordinates LLM streaming with sentence-buffered TTS for low latency. Uses `SentenceBuffer` to extract complete sentences.
- **llm.py**: LLM service wrapper.

### Database (`database/`)
- Async SQLite via aiosqlite
- Tables: conversations, messages, entities, events, journals, ratings, settings
- Settings use Fernet encryption for secrets
- Migrations in `database/migrations/`

### Plugins (`plugins/`)
- Tools use Strands `@tool` decorator
- Built-in: conversation_tool, datetime_tool, entity_tool, event_tool, journal_tool, rating_tool, weather_tool
- Auto-discovered and hot-reloadable

## Key Patterns

- **Async-first**: All I/O is async (database, LLM, TTS)
- **Streaming**: WebSocket streams text chunks + TTS audio in real-time; sentences buffered for low-latency audio
- **Singleton caching**: Agent instance cached globally with async lock
- **Two-tier plugins**: Built-in (auto-loaded) + runtime-installed (via ZIP/tar with plugin.yaml manifest)
- **Config hierarchy**: YAML config (`config.yaml`) → database settings → environment variables for API keys

## Testing

Tests use pytest with FastAPI's TestClient. Async tests via pytest-asyncio. Test files mirror the module structure in `tests/`.
