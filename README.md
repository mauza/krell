# Krell

Agentic AI backend powered by [Strands](https://github.com/emcie-co/strands) with tool calling, persistent memory, and low-latency TTS.

## 🚀 Quick Start

### Installation

**Using uv (recommended):**
```bash
# Install dependencies
uv sync

# Run server
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

**Using pip:**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Setup Ollama (Local LLM)

```bash
# Install Ollama (see https://ollama.ai)
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3.1:8b
```

Server starts at: **http://localhost:8000**  
Dashboard at: **http://localhost:8000/dashboard**  
API docs at: **http://localhost:8000/docs**

## 📡 API Endpoints

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Root endpoint (welcome message) |
| `GET` | `/api/health` | Health check |
| `GET` | `/api/config` | Backend config + loaded plugins |

### Chat

| Method | Endpoint | Body | Returns |
|--------|----------|------|---------|
| `POST` | `/api/chat` | `{"message": "...", "conversation_id": "..."}` | Chat response + conversation_id + tool_calls |
| `POST` | `/api/chat-with-tts` | `{"message": "...", "session_id": 123}` | JSON header + WAV audio bytes |

**Note:** `/api/chat` auto-creates conversation if `conversation_id` is null.

### Conversations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/conversations?limit=100` | List all conversations (newest first) |
| `GET` | `/api/conversations/{id}` | Get conversation with all messages |
| `DELETE` | `/api/conversations/{id}` | Delete conversation (cascades to messages) |
| `PATCH` | `/api/conversations/{id}` | Update conversation title |

### Journal

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/journal?entry_type=...&limit=50` | List journal entries (filter by type) |
| `GET` | `/api/journal/{id}` | Get specific journal entry |
| `DELETE` | `/api/journal/{id}` | Delete journal entry |

**Entry types:** `autonomous`, `user_requested`

### Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/settings` | Get all settings (API keys masked as `••••••••`) |
| `POST` | `/api/settings` | Update settings (encrypts sensitive values) |

**Sensitive keys:** `api_key`, `openai_api_key`, `anthropic_api_key`

### Dashboard (Web UI)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/dashboard` | Main dashboard UI (HTMX + Tailwind) |
| `GET` | `/dashboard/api/status` | System status (uptime, counts) |
| `GET` | `/dashboard/api/settings` | Get LLM settings for form |
| `POST` | `/dashboard/api/settings` | Update LLM settings |
| `POST` | `/dashboard/api/test-connection` | Test LLM connection |
| `GET` | `/dashboard/api/plugins` | Get loaded plugins metadata |
| `POST` | `/dashboard/api/reload-plugins` | Manual plugin reload |
| `GET` | `/dashboard/api/recent-conversations` | Last 10 conversations |
| `GET` | `/dashboard/api/recent-journal` | Last 10 journal entries |

## 🔧 Configuration

### config.yaml

```yaml
# LLM Configuration
llm_endpoint: "http://localhost:11434"  # Ollama or OpenAI endpoint
llm_model: "llama3.1:8b"                # Model name
llm_provider: "ollama"                   # or "openai"
llm_openai_api_key: ""                   # Only for OpenAI

# TTS Configuration
tts_provider: "kyutai"
tts_voice: "expresso/ex04-ex03_fast_001_channel1_208s.wav"
tts_format: "wav"                        # Audio format
tts_model_path: "./models/kyutai-tts-1.6b"
tts_voices_path: "./models/kyutai-voices"
tts_device: "auto"                       # or "cuda" or "cpu"
tts_mode: "direct"

# Database
database_path: "./data/krell.db"

# Server
host: "0.0.0.0"
port: 8000
```

### Runtime Settings (via API/Dashboard)

Settings stored in database, editable via dashboard:

- **llm_endpoint** - LLM API endpoint
- **llm_model** - Model name
- **api_key** - API key (encrypted)
- **tts_voice** - TTS voice ID

## 🔌 Plugin System

### Available Plugins

1. **search_past_conversations** - Semantic search through conversation history
2. **save_journal_entry** - Create journal entries (autonomous or user-requested)
3. **get_journal_entries** - Retrieve journal entries by type
4. **add_numbers** - Example tool (demo)
5. **echo_message** - Example tool (demo)

### Creating Plugins

Create a new file in `backend/plugins/`:

```python
from strands import tool

@tool
def my_custom_tool(param: str) -> str:
    """
    Description of what this tool does.
    The LLM sees this docstring.
    
    Args:
        param: Parameter description
        
    Returns:
        What the tool returns
    """
    # Your logic here
    return f"Result: {param}"
```

**Features:**
- ✅ Hot-reload (no server restart needed!)
- ✅ Auto-discovery (just add file to `/plugins/`)
- ✅ Syntax error handling
- ✅ Thread-safe reloading

## 🗄️ Database Schema

### Tables

**conversations**
- `id` (TEXT, PK) - UUID
- `title` (TEXT)
- `created_at` (TEXT, ISO8601)
- `updated_at` (TEXT, ISO8601)

**messages**
- `id` (TEXT, PK) - UUID
- `conversation_id` (TEXT, FK → conversations.id, CASCADE)
- `role` (TEXT) - "user" | "assistant" | "system"
- `content` (TEXT)
- `tool_calls` (TEXT, JSON)
- `timestamp` (TEXT, ISO8601)

**journal_entries**
- `id` (TEXT, PK) - UUID
- `content` (TEXT)
- `entry_type` (TEXT) - "autonomous" | "user_requested"
- `conversation_id` (TEXT, FK → conversations.id, SET NULL)
- `created_at` (TEXT, ISO8601)

**settings**
- `key` (TEXT, PK)
- `value` (TEXT) - May be encrypted (Fernet)

### Encryption

Sensitive settings (API keys) are encrypted using **Fernet** (symmetric encryption).

- Key stored in `data/.encryption_key` (auto-generated)
- Only these keys are encrypted: `api_key`, `openai_api_key`, `anthropic_api_key`

## 🧪 Testing

```bash
# Run all tests (88 tests)
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_api_endpoints.py -v

# Run with coverage
uv run pytest tests/ --cov=. --cov-report=html

# Run specific test
uv run pytest tests/test_api_endpoints.py::test_chat_creates_new_conversation -v
```

### Test Structure

```
tests/
├── test_agent.py              # KrellAgent tests (14 tests)
├── test_api_endpoints.py      # REST API tests (14 tests)
├── test_conversation_tool.py  # Conversation search tool (7 tests)
├── test_dashboard.py          # Dashboard endpoints (9 tests)
├── test_database.py           # Database operations (16 tests)
├── test_journal_tool.py       # Journal tool (6 tests)
└── test_plugin_loader.py      # Plugin system (12 tests)
```

All tests use temporary databases and clean up automatically.

## 🐳 Docker

**Build:**
```bash
docker build -t krell .
```

**Run:**
```bash
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  krell
```

**Docker Compose (recommended):**
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
      - OLLAMA_HOST=http://host.docker.internal:11434
```

## 📊 Dashboard

Access at **http://localhost:8000/dashboard**

**Features:**
- System status (uptime, conversation count, journal entries)
- LLM configuration (endpoint, model, API key)
- Test LLM connection
- View loaded plugins
- Manual plugin reload
- Recent activity (conversations & journal)

**Auto-updates:**
- System status: Every 5 seconds
- Recent activity: Every 10 seconds

## 🔍 Debugging

### Logs

Server logs to stdout. Use systemd, pm2, or redirect:

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 2>&1 | tee krell.log
```

### Common Issues

**Model not found:**
```
ResponseError: model "llama3.1:8b" not found
```
→ Pull model: `ollama pull llama3.1:8b`

**TTS errors:**
```
Kyutai TTS model not initialized
```
→ Download models:
- Model: https://huggingface.co/kyutai/tts-1.6b-en_fr
- Voices: https://huggingface.co/kyutai/tts-voices
Extract to `backend/models/kyutai-tts-1.6b/` and `backend/models/kyutai-voices/`

**Database locked:**
```
database is locked
```
→ Close other connections, use WAL mode (automatic)

## 🚢 Production Deployment

### Recommended Stack

- **Nginx** - Reverse proxy
- **Systemd** - Process management
- **Ollama** - Local LLM inference
- **SQLite** - Database (auto-backup recommended)

### Example systemd service

```ini
[Unit]
Description=Krell
After=network.target

[Service]
Type=simple
User=krell
WorkingDirectory=/opt/krell
ExecStart=/opt/krell/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=on-failure
Environment="PATH=/opt/krell/.venv/bin:/usr/bin"

[Install]
WantedBy=multi-user.target
```

### Security

- ⚠️ **Dashboard has NO authentication** - Add auth or firewall it
- ✅ API keys are encrypted at rest
- ✅ Use HTTPS in production (reverse proxy)
- ✅ Restrict network access to trusted clients

## 📝 Notes

- **Agentic mode** always enabled (not configurable yet)
- **Vector embeddings** removed (not needed for current tools)
- **ChromaDB** removed (simplified to SQLite only)
- **Legacy endpoints** maintained for backward compatibility
- **Plugin hot-reload** uses watchdog (file system monitoring)

## 🔗 Links

- [Strands Framework](https://github.com/emcie-co/strands)
- [Kyutai TTS](https://huggingface.co/kyutai/tts-1.6b-en_fr)
- [Ollama](https://ollama.ai)
- [FastAPI Docs](https://fastapi.tiangolo.com)

## 📄 License

MIT
