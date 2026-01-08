# Krell Realtime API Reference

Quick reference for the OpenAI Realtime API compatible endpoint.

## Endpoint

```
ws://localhost:8000/v1/realtime
```

## Protocol

WebSocket with JSON messages using OpenAI Realtime API format.

## Client → Server Events

### input_audio_buffer.append

Send audio chunk to the server.

```json
{
  "type": "input_audio_buffer.append",
  "audio": "base64_encoded_opus_audio"
}
```

**Audio format**: Base64-encoded Opus audio (24kHz, mono)

### session.update

Update session configuration.

```json
{
  "type": "session.update",
  "session": {
    "voice": "tara",
    "instructions": "You are a helpful assistant",
    "input_audio_format": "opus",
    "output_audio_format": "opus"
  }
}
```

### response.cancel

Cancel ongoing response (interruption).

```json
{
  "type": "response.cancel"
}
```

## Server → Client Events

### session.created

Session initialized.

```json
{
  "type": "session.created",
  "session": {
    "voice": "tara",
    "input_audio_format": "opus",
    "output_audio_format": "opus"
  }
}
```

### conversation.item.input_audio_transcription.completed

User's speech was transcribed.

```json
{
  "type": "conversation.item.input_audio_transcription.completed",
  "item_id": "uuid",
  "transcript": "Hello, how are you?"
}
```

### response.text.delta

Streaming text from LLM.

```json
{
  "type": "response.text.delta",
  "delta": "I'm doing ",
  "item_id": "uuid"
}
```

### response.audio.delta

Streaming audio (TTS output).

```json
{
  "type": "response.audio.delta",
  "delta": "base64_encoded_opus_audio",
  "item_id": "uuid"
}
```

**Audio format**: Base64-encoded Opus audio (24kHz, mono)

### response.done

Response generation complete.

```json
{
  "type": "response.done",
  "response": {
    "id": "uuid"
  }
}
```

### error

Server error.

```json
{
  "type": "error",
  "error": {
    "type": "server_error",
    "message": "Error description"
  }
}
```

## Audio Format

- **Codec**: Opus
- **Sample Rate**: 24kHz
- **Channels**: Mono (1)
- **Encoding**: Base64
- **Frame Duration**: 20ms (recommended)

## Example Flow

```
1. Browser → Server: Connect WebSocket
2. Server → Browser: session.created
3. Browser → Server: input_audio_buffer.append (user speaks)
4. Browser → Server: input_audio_buffer.append (user speaks)
5. Server → Browser: input_audio_buffer.committed
6. Server → Browser: conversation.item.input_audio_transcription.completed
7. Server → Browser: response.created
8. Server → Browser: response.text.delta (streaming)
9. Server → Browser: response.audio.delta (streaming)
10. Server → Browser: response.done
11. (Repeat from step 3)
```

## JavaScript Example

```javascript
const ws = new WebSocket('ws://localhost:8000/v1/realtime');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'response.audio.delta') {
    // Decode and play audio
    const audioData = atob(data.delta);
    playOpusAudio(audioData);
  }
  
  else if (data.type === 'conversation.item.input_audio_transcription.completed') {
    console.log('You said:', data.transcript);
  }
};

// Send audio
function sendAudio(base64Opus) {
  ws.send(JSON.stringify({
    type: 'input_audio_buffer.append',
    audio: base64Opus
  }));
}
```

## Health Check

```bash
curl http://localhost:8000/v1/realtime/health
```

Returns:
```json
{
  "status": "healthy",
  "tts_ready": true,
  "stt_ready": true,
  "available_slots": 4,
  "max_concurrent_sessions": 4
}
```

## Rate Limits

- **Max concurrent sessions**: 4 (configurable)
- **Audio chunk size**: No hard limit, but 100-200ms chunks recommended
- **Message size**: No enforced limit

## Error Codes

- `invalid_request_error` - Malformed request
- `server_error` - Internal server error
- `authentication_error` - Authentication failed (if enabled)
- `rate_limit_error` - Too many concurrent connections
