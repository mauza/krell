# API Reference

Krell provides a REST API and WebSocket interface for interacting with the AI agent.

**Base URL:** `http://localhost:8000`

**Interactive Docs:** `http://localhost:8000/docs` (Swagger UI)

## Authentication

Currently, Krell does not implement authentication. For production deployments, add authentication via a reverse proxy or custom middleware.

## Core Endpoints

### Health Check

```http
GET /api/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### Configuration

```http
GET /api/config
```

**Response:**
```json
{
  "agentic_enabled": true,
  "loaded_plugins": ["create_entity", "search_entities", "get_weather"]
}
```

## Chat

### WebSocket Chat (Recommended)

```
WS /api/ws/chat
```

WebSocket endpoint for real-time streaming chat with the AI agent.

**Connect:**
```javascript
const ws = new WebSocket('ws://localhost:8000/api/ws/chat');
```

**Send Message:**
```json
{
  "message": "Hello!",
  "conversation_id": null
}
```

**Receive Events:**
```json
{"type": "conversation_id", "conversation_id": "abc-123"}
{"type": "text", "content": "Hello"}
{"type": "text", "content": "! How"}
{"type": "tool_call", "name": "get_weather", "input": {"location": "NYC"}}
{"type": "tool_result", "content": "{\"temp\": 72}"}
{"type": "done", "full_text": "Hello! How can I help?", "tool_calls": []}
```

## Conversations

### List Conversations

```http
GET /api/conversations?limit=100
```

**Response:**
```json
[
  {
    "id": "abc-123",
    "title": "Weather inquiry",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:35:00Z"
  }
]
```

### Get Conversation

```http
GET /api/conversations/{conversation_id}
```

**Response:**
```json
{
  "id": "abc-123",
  "title": "Weather inquiry",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:35:00Z",
  "messages": [
    {
      "id": "msg-1",
      "role": "user",
      "content": "What's the weather in NYC?",
      "timestamp": "2024-01-15T10:30:00Z",
      "tool_calls": null
    },
    {
      "id": "msg-2",
      "role": "assistant",
      "content": "The weather in NYC is currently 72°F and sunny.",
      "timestamp": "2024-01-15T10:30:05Z",
      "tool_calls": [{"name": "get_weather", "input": {"location": "NYC"}}]
    }
  ]
}
```

### Update Conversation Title

```http
PATCH /api/conversations/{conversation_id}
Content-Type: application/json

{
  "title": "New Title"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Title updated successfully"
}
```

### Delete Conversation

```http
DELETE /api/conversations/{conversation_id}
```

**Response:**
```json
{
  "success": true,
  "message": "Conversation deleted successfully"
}
```

## Text-to-Speech

### Stream TTS Audio

```http
POST /api/tts/stream
Content-Type: application/json

{
  "text": "Hello, world!",
  "voice": "expresso/ex04-ex03_fast_001_channel1_208s.wav",
  "format": "wav"
}
```

**Response:** Streaming audio (chunked transfer encoding)

### Stream TTS (GET)

```http
GET /api/tts/stream?text=Hello&voice=...&format=wav
```

Useful for direct playback in browsers via `<audio>` elements.

## Sessions (Legacy)

Legacy session-based API for backward compatibility.

### Create Session

```http
POST /api/sessions
Content-Type: application/json

{
  "title": "New Chat"
}
```

### List Sessions

```http
GET /api/sessions?limit=100
```

### Get Session Messages

```http
GET /api/sessions/{session_id}
```

### Add Message to Session

```http
POST /api/sessions/{session_id}/messages
Content-Type: application/json

{
  "session_id": 1,
  "user_message": "Hello",
  "ai_response": "Hi there!"
}
```

### Update Session Title

```http
PUT /api/sessions/{session_id}/title
Content-Type: application/json

{
  "title": "Updated Title"
}
```

### Delete Session

```http
DELETE /api/sessions/{session_id}
```

## Admin Endpoints

### Reload Plugins

```http
POST /api/admin/reload-plugins
```

**Response:**
```json
{
  "success": true,
  "message": "Plugins reloaded successfully",
  "tools_count": 10,
  "plugins_loaded": 7,
  "plugins_failed": 0,
  "plugins": [
    {
      "filename": "entity_tool.py",
      "status": "loaded",
      "tools": ["create_entity", "update_entity", "search_entities"],
      "load_time": 0.023
    }
  ]
}
```

### Get Plugins Info

```http
GET /api/admin/plugins
```

**Response:**
```json
{
  "tools_count": 10,
  "plugins_loaded": 7,
  "plugins_failed": 0,
  "plugins": [...],
  "tool_names": ["create_entity", "update_entity", ...]
}
```

### Reload Agent

```http
POST /api/admin/reload-agent
```

Forces the AI agent to reinitialize with current settings.

**Response:**
```json
{
  "success": true,
  "message": "Agent reloaded successfully",
  "model": "gpt-4o-mini",
  "endpoint": "https://api.openai.com"
}
```

## Dashboard Endpoints

These endpoints power the web dashboard at `/dashboard`.

### System Status

```http
GET /dashboard/api/status
```

**Response:**
```json
{
  "uptime": "2h 30m",
  "total_conversations": 42,
  "total_journal_entries": 15
}
```

### Get Settings

```http
GET /dashboard/api/settings
```

**Response:**
```json
{
  "llm_endpoint": "https://api.openai.com",
  "llm_model": "gpt-4o-mini",
  "llm_provider": "openai",
  "api_key": "••••••••"
}
```

### Update Settings

```http
POST /dashboard/api/settings
Content-Type: application/x-www-form-urlencoded

llm_endpoint=https://api.openai.com&llm_model=gpt-4o&api_key=sk-...
```

### Test LLM Connection

```http
POST /dashboard/api/test-connection
Content-Type: application/json

{
  "endpoint": "https://api.openai.com",
  "model": "gpt-4o-mini",
  "provider": "openai"
}
```

**Response:**
```json
{
  "success": true,
  "latency_ms": 150,
  "provider": "openai"
}
```

### Get Plugins

```http
GET /dashboard/api/plugins
```

### Reload Plugins

```http
POST /dashboard/api/plugins/reload
```

### Recent Conversations

```http
GET /dashboard/api/recent/conversations
```

### Recent Journal Entries

```http
GET /dashboard/api/recent/journal
```

## Error Responses

All endpoints return errors in this format:

```json
{
  "detail": "Error message here"
}
```

**Common HTTP Status Codes:**

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request (invalid parameters) |
| 404 | Not Found |
| 500 | Internal Server Error |

## Rate Limiting

Krell does not implement rate limiting by default. For production, add rate limiting via:
- Reverse proxy (Nginx, Caddy)
- FastAPI middleware
- API gateway

## Examples

### cURL

```bash
# Health check
curl http://localhost:8000/api/health

# List conversations
curl http://localhost:8000/api/conversations

# Delete conversation
curl -X DELETE http://localhost:8000/api/conversations/abc-123

# Update title
curl -X PATCH http://localhost:8000/api/conversations/abc-123 \
  -H "Content-Type: application/json" \
  -d '{"title": "New Title"}'

# Stream TTS
curl "http://localhost:8000/api/tts/stream?text=Hello" --output hello.wav
```

### Python

```python
import requests

# List conversations
response = requests.get("http://localhost:8000/api/conversations")
conversations = response.json()

# WebSocket chat
import websockets
import asyncio
import json

async def chat():
    async with websockets.connect("ws://localhost:8000/api/ws/chat") as ws:
        await ws.send(json.dumps({
            "message": "Hello!",
            "conversation_id": None
        }))
        
        async for message in ws:
            event = json.loads(message)
            if event["type"] == "text":
                print(event["content"], end="", flush=True)
            elif event["type"] == "done":
                print()
                break

asyncio.run(chat())
```

### JavaScript

```javascript
// REST API
const response = await fetch('http://localhost:8000/api/conversations');
const conversations = await response.json();

// WebSocket chat
const ws = new WebSocket('ws://localhost:8000/api/ws/chat');

ws.onopen = () => {
  ws.send(JSON.stringify({
    message: 'Hello!',
    conversation_id: null
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'text') {
    console.log(data.content);
  }
};
```
