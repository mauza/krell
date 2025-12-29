# Configuration Guide

Krell is configured through `config.yaml` in the project root. This guide covers all available options.

## Quick Reference

```yaml
# Minimal configuration for OpenAI
llm:
  model: "gpt-4o-mini"
  endpoint: "https://api.openai.com"
  openai_api_key: "sk-..."  # Or use OPENAI_API_KEY env var

database:
  path: "./data/krell.db"

server:
  host: "0.0.0.0"
  port: 8000
```

## Complete Configuration Reference

### LLM Configuration

```yaml
llm:
  model: "gpt-4o-mini"              # Model name
  endpoint: "https://api.openai.com" # OpenAI-compatible API endpoint
  openai_api_key: ""                 # API key (prefer env var instead)
```

**Supported Providers:**

| Provider | Endpoint | Example Model |
|----------|----------|---------------|
| OpenAI | `https://api.openai.com` | `gpt-4o-mini`, `gpt-4o` |
| Ollama | `http://localhost:11434` | `llama3.1:8b`, `mistral` |
| OpenRouter | `https://openrouter.ai/api` | `anthropic/claude-3-haiku` |
| Any OpenAI-compatible | Your endpoint URL | Your model name |

**Environment Variables:**

```bash
export OPENAI_API_KEY="your-api-key"  # Preferred over config file
```

### Database Configuration

```yaml
database:
  path: "./data/krell.db"  # SQLite database path
```

The database file is created automatically on first run. The `data/` directory will be created if it doesn't exist.

**Data stored:**
- Conversations and messages
- Entities (people, places, things)
- Events and journals
- Ratings
- Runtime settings (encrypted API keys)

### Server Configuration

```yaml
server:
  host: "0.0.0.0"  # Bind address (0.0.0.0 for all interfaces)
  port: 8000       # HTTP port
```

### TTS Configuration

```yaml
tts:
  provider: "kyutai"           # TTS provider
  mode: "direct"               # "direct" (in-process), "cli", or "server"
  format: "wav"                # Audio format
  lang: "en-us"                # Language
  speed: 1.0                   # Playback speed multiplier
  device: "auto"               # "auto", "cuda", or "cpu"
  chunk_size: 4096             # Audio chunk size for streaming
  max_text_length: 400         # Max characters per TTS chunk
  
  streaming:
    enabled: true              # Enable streaming TTS
    min_sentence_length: 20    # Min chars before generating TTS
    tool_pause_duration: 0.5   # Seconds of silence during tool execution
  
  kyutai:
    model_path: "./models/kyutai-tts-1.6b"
    voices_path: "./models/kyutai-voices"
    voice: "expresso/ex04-ex03_fast_001_channel1_208s.wav"
```

**Setting up Kyutai TTS:**

1. Download the model from [HuggingFace](https://huggingface.co/kyutai/tts-1.6b-en_fr)
2. Download voices from [HuggingFace](https://huggingface.co/kyutai/tts-voices)
3. Extract to the configured paths

### Embeddings Configuration

```yaml
embeddings:
  provider: "local"            # "local" or "openai"
  model: "all-MiniLM-L6-v2"    # Local model name
  openai_api_key: ""           # Only needed for OpenAI provider
```

### Vector Store Configuration

```yaml
vector_store:
  collection_name: "krell_conversations"
  persist_directory: "./data/chroma_db"
```

### Agentic Workflows

```yaml
agentic:
  enabled: false
  workflows: []
```

### Weather API

```yaml
openweather_api_key: "your_api_key_here"  # From openweathermap.org
```

## Environment Variables

Krell supports these environment variables (override config file):

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENWEATHER_API_KEY` | OpenWeatherMap API key |

## Runtime Settings

Some settings can be changed at runtime via the dashboard or API without restarting:

- LLM endpoint and model
- API keys (stored encrypted)
- TTS voice

Access via:
- Dashboard: http://localhost:8000/dashboard
- API: `GET/POST /api/settings`

## Configuration Examples

### Local Development with Ollama

```yaml
llm:
  model: "llama3.1:8b"
  endpoint: "http://localhost:11434"
  openai_api_key: "ollama"  # Ollama doesn't need a real key

database:
  path: "./data/krell.db"

server:
  host: "127.0.0.1"
  port: 8000

tts:
  provider: "kyutai"
  device: "cpu"  # Use CPU if no GPU
```

### Production with OpenAI

```yaml
llm:
  model: "gpt-4o"
  endpoint: "https://api.openai.com"
  # Use OPENAI_API_KEY env var instead of config file

database:
  path: "/var/lib/krell/krell.db"

server:
  host: "127.0.0.1"  # Behind reverse proxy
  port: 8000

tts:
  provider: "kyutai"
  device: "cuda"
```

### Using OpenRouter

```yaml
llm:
  model: "anthropic/claude-3-haiku"
  endpoint: "https://openrouter.ai/api/v1"
  openai_api_key: "sk-or-..."  # OpenRouter API key
```

## Troubleshooting

### "API key is required"

Set your API key via environment variable:
```bash
export OPENAI_API_KEY="your-key"
```

Or in config.yaml (less secure):
```yaml
llm:
  openai_api_key: "your-key"
```

### "Model not found" (Ollama)

Pull the model first:
```bash
ollama pull llama3.1:8b
```

### Database locked

SQLite is being accessed by multiple processes. Close other connections or restart the server.

### TTS not working

1. Check that model files are downloaded
2. Verify paths in config match actual locations
3. Try `device: "cpu"` if GPU issues occur
