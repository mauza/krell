# Unmute Integration Guide for Krell

This guide explains how Unmute works and how to adapt their approach to make Krell support real-time voice conversations.

## Unmute Architecture Overview

Unmute enables **real-time voice conversations with LLMs** by orchestrating:
1. **STT (Speech-to-Text)**: Kyutai's streaming STT model
2. **LLM**: Any OpenAI-compatible text LLM (vLLM, Mistral, GPT-4, etc.)
3. **TTS (Text-to-Speech)**: Kyutai's streaming TTS model

The key innovation is **streaming all components in parallel** for ultra-low latency:
- Browser sends audio → STT transcribes → LLM generates → TTS speaks → Browser plays
- All steps happen **concurrently**, not sequentially

## Key Architecture Patterns

### 1. Dual Loop WebSocket Pattern

Unmute uses **two concurrent async loops**:

```python
# Main WebSocket handler
async def websocket_route(websocket: WebSocket):
    async with SEMAPHORE:  # Limit concurrent connections
        await websocket.accept(subprotocol="realtime")
        
        handler = UnmuteHandler()
        emit_queue = asyncio.Queue()
        
        async with asyncio.TaskGroup() as tg:
            # Two loops running concurrently
            tg.create_task(receive_loop(websocket, handler, emit_queue))
            tg.create_task(emit_loop(websocket, handler, emit_queue))
```

**receive_loop**: Handles incoming messages from browser
- Receives Opus-encoded audio chunks (base64)
- Decodes Opus → PCM audio
- Sends to STT via handler

**emit_loop**: Sends messages to browser
- Pulls events from handler's internal queue
- Converts audio to Opus format
- Base64 encodes and sends to browser

### 2. Opus Audio Streaming

Unmute uses **Opus codec** for efficient real-time audio streaming:

```python
# Receiving audio from browser
opus_reader = sphn.OpusStreamReader(SAMPLE_RATE)
opus_bytes = base64.b64decode(message.audio)
pcm = await asyncio.to_thread(opus_reader.append_bytes, opus_bytes)

# Sending audio to browser
opus_writer = sphn.OpusStreamWriter(SAMPLE_RATE)
opus_bytes = await asyncio.to_thread(opus_writer.append_pcm, audio)
base64_audio = base64.b64encode(opus_bytes).decode("utf-8")
```

**Why Opus?**
- Very low latency (~20ms frames)
- Excellent compression (~32-48kbps for voice)
- Browser native support
- Handles packet loss gracefully

### 3. Handler Pattern

The `UnmuteHandler` class orchestrates the entire pipeline:

```python
class UnmuteHandler:
    async def receive(self, audio_chunk):
        """Process incoming audio from user"""
        # 1. Send to STT service (WebSocket)
        # 2. Buffer transcription
        # 3. Detect end-of-speech
        # 4. Trigger LLM response
        
    async def emit(self):
        """Yield next event/audio for browser"""
        # 1. Check internal event queue
        # 2. Return next event (text/audio/metadata)
        # 3. None if queue empty (non-blocking)
```

The handler maintains:
- **WebSocket connections** to STT/TTS services
- **Internal queues** for events
- **State machine** for conversation flow
- **Turn-taking logic** (VAD, interruptions)

### 4. OpenAI Realtime API Protocol

Unmute uses the [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime) protocol format:

**Client → Server events:**
```typescript
interface InputAudioBufferAppend {
  type: "input_audio_buffer.append"
  audio: string  // base64 Opus
}

interface SessionUpdate {
  type: "session.update"
  session: {
    voice?: string
    instructions?: string
  }
}
```

**Server → Client events:**
```typescript
interface ResponseAudioDelta {
  type: "response.audio.delta"
  delta: string  // base64 Opus
}

interface ResponseTextDelta {
  type: "response.text.delta"
  delta: string
}
```

This protocol provides:
- Standard format clients can use
- Clean event-driven architecture
- Easy to extend with custom events

## Comparison: Unmute vs Current Krell

| Aspect | Unmute | Current Krell |
|--------|--------|---------------|
| **Audio Format** | Opus (streaming codec) | WAV (complete files) |
| **Protocol** | OpenAI Realtime API | Custom JSON events |
| **STT** | Kyutai streaming STT | None (text-only) |
| **TTS Strategy** | Stream as LLM generates | Wait for complete response |
| **Audio Transport** | Base64 over WebSocket | Binary WebSocket frames |
| **Loop Pattern** | Dual loops (receive/emit) | Single message handler |
| **Connection Limit** | Semaphore (4 clients) | Unlimited |

## Recommended Krell Integration Path

### Phase 1: Add STT Support (Voice Input)

**Goal**: Let users speak instead of type

```python
# New file: api/voice_input.py

from faster_whisper import WhisperModel

class VoiceInputHandler:
    """Handle voice input from users via WebSocket"""
    
    def __init__(self):
        self.model = WhisperModel("base", device="cuda")
        
    async def transcribe_audio(self, audio_bytes: bytes) -> str:
        """Convert audio to text using Whisper"""
        # Save to temp file
        # Run Whisper
        # Return transcription
        pass
```

**WebSocket protocol addition:**
```typescript
// Client sends
{
  "type": "voice_input",
  "audio": "base64_wav_data"
}

// Server responds
{
  "type": "transcription",
  "text": "transcribed text"
}
// Then proceeds with normal chat flow
```

**Pros**: Simple, works with existing infrastructure
**Cons**: Not real-time (need complete audio file)

### Phase 2: Streaming TTS (Already Implemented!)

Your `tts_streaming.py` is excellent! It already implements:
- ✅ Sentence buffering
- ✅ Immediate TTS generation
- ✅ Streaming audio output

**To align with Unmute style:**
```python
# Consider switching from WAV to Opus for efficiency

import opuslib

async def stream_tts_realtime(...):
    opus_encoder = opuslib.Encoder(24000, 1, opuslib.APPLICATION_VOIP)
    
    for sentence in sentences:
        audio_data, rate = await _generate_tts_for_sentence(...)
        
        # Encode to Opus instead of WAV
        opus_bytes = opus_encoder.encode(audio_data.tobytes(), 960)
        base64_opus = base64.b64encode(opus_bytes).decode('utf-8')
        
        yield {
            "type": "audio.delta",
            "format": "opus",
            "delta": base64_opus
        }
```

### Phase 3: Full Real-Time Pipeline (The Unmute Way)

**Goal**: True streaming voice conversations like Unmute

This requires:
1. **Streaming STT** (not Whisper - use Kyutai or similar)
2. **Dual-loop WebSocket** pattern
3. **Opus codec** for audio
4. **Handler class** orchestrating the flow

```python
# New file: api/realtime.py

@router.websocket("/v1/realtime")
async def realtime_endpoint(websocket: WebSocket):
    """OpenAI Realtime API compatible endpoint"""
    
    async with REALTIME_SEMAPHORE:
        await websocket.accept(subprotocol="realtime")
        
        handler = KrellRealtimeHandler(
            stt_url=config.stt_websocket_url,
            tts_service=tts_service,
            agent=krell_agent
        )
        
        emit_queue = asyncio.Queue()
        
        async with asyncio.TaskGroup() as tg:
            tg.create_task(receive_loop(websocket, handler, emit_queue))
            tg.create_task(emit_loop(websocket, handler, emit_queue))
```

## Audio Pipeline Comparison

### Unmute Audio Flow
```
Browser Microphone
  → Opus Encode (browser native)
  → WebSocket base64 chunks
  → Backend Opus Decode
  → STT WebSocket (PCM)
  → Transcription
  → LLM
  → TTS WebSocket (PCM)
  → Backend Opus Encode
  → WebSocket base64 chunks
  → Browser Opus Decode (native)
  → Speaker
```

### Current Krell Flow
```
Browser (text input only)
  → WebSocket JSON
  → Agent.chat_stream()
  → TTS synthesis per sentence
  → WAV file creation
  → WebSocket binary
  → Browser Audio API
  → Speaker
```

## Critical Implementation Details

### 1. Opus Integration

```python
# Install: pip install opuslib

# Encoder (for sending audio to browser)
encoder = opuslib.Encoder(
    fs=24000,           # Sample rate
    channels=1,          # Mono
    application=opuslib.APPLICATION_VOIP  # Optimized for voice
)

# Frame size must be 2.5, 5, 10, 20, 40, or 60 ms
frame_size = 960  # 40ms at 24kHz

# Encode PCM to Opus
opus_bytes = encoder.encode(pcm_bytes, frame_size)

# Decoder (for receiving audio from browser)
decoder = opuslib.Decoder(fs=24000, channels=1)
pcm_bytes = decoder.decode(opus_bytes, frame_size)
```

### 2. WebSocket Backpressure Handling

```python
# From Unmute's emit_loop
async def emit_loop(websocket, handler, emit_queue):
    while True:
        # Non-blocking check of manual queue
        try:
            event = emit_queue.get_nowait()
        except asyncio.QueueEmpty:
            # Pull from handler (may return None)
            event = await handler.emit()
            if event is None:
                await asyncio.sleep(0.001)  # Tiny sleep to avoid busy loop
                continue
        
        # Send to client
        await websocket.send_text(event.model_dump_json())
```

This pattern:
- Prevents blocking on I/O
- Handles both queued events and streaming audio
- Avoids backpressure issues

### 3. Connection Limiting

```python
# Limit concurrent connections to avoid GPU OOM
MAX_CLIENTS = 4  # Adjust based on GPU memory
SEMAPHORE = asyncio.Semaphore(MAX_CLIENTS)

@app.websocket("/v1/realtime")
async def endpoint(websocket):
    async with SEMAPHORE:
        # Connection established
        # Will wait here if 4 clients already connected
        await handle_connection(websocket)
```

### 4. Health Checks

```python
# Unmute checks all services before accepting connections
@app.get("/v1/health")
async def get_health():
    health = await _get_health(None)
    return health

async def _get_health(_):
    async with asyncio.TaskGroup() as tg:
        tts_up = tg.create_task(check_service(TTS_SERVER))
        stt_up = tg.create_task(check_service(STT_SERVER))
        llm_up = tg.create_task(check_service(LLM_SERVER))
    
    return HealthStatus(
        tts_up=await tts_up,
        stt_up=await stt_up,
        llm_up=await llm_up
    )
```

## Recommended Next Steps for Krell

### Option A: Minimal Changes (Voice Input Only)
1. Add Whisper-based STT endpoint
2. Client sends complete audio files
3. Server transcribes and processes as text
4. Use existing TTS streaming

**Effort**: Low | **Latency**: Medium | **UX**: Good

### Option B: Hybrid Approach (Recommended)
1. Keep current text chat working as-is
2. Add **parallel** voice mode using Unmute patterns:
   - Opus audio streaming
   - Dual-loop WebSocket
   - Kyutai STT/TTS services
3. Let users choose text or voice mode

**Effort**: Medium | **Latency**: Low | **UX**: Excellent

### Option C: Full Unmute Clone
1. Implement complete OpenAI Realtime API
2. Deploy Kyutai STT/TTS as separate services
3. Rewrite frontend for real-time audio
4. Support interruptions, turn-taking, etc.

**Effort**: High | **Latency**: Minimal | **UX**: Best-in-class

## Code Examples for Krell

### Simple Voice Input (Option A)

```python
# api/routes.py additions

from faster_whisper import WhisperModel

whisper_model = None

def get_whisper():
    global whisper_model
    if whisper_model is None:
        whisper_model = WhisperModel("base", device="cuda")
    return whisper_model

@router.post("/api/transcribe")
async def transcribe_audio(file: UploadFile):
    """Transcribe uploaded audio file to text"""
    import tempfile
    
    # Save upload to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Transcribe
        model = get_whisper()
        segments, info = await asyncio.to_thread(
            model.transcribe,
            tmp_path,
            language="en"
        )
        
        # Combine segments
        text = " ".join([seg.text for seg in segments])
        
        return {"text": text}
    
    finally:
        os.unlink(tmp_path)
```

### Opus Streaming Audio (Option B)

```python
# services/opus_streaming.py

import opuslib
import base64
from typing import AsyncGenerator

class OpusAudioStreamer:
    """Stream audio using Opus codec"""
    
    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate
        self.encoder = opuslib.Encoder(
            fs=sample_rate,
            channels=1,
            application=opuslib.APPLICATION_VOIP
        )
        self.frame_size = 960  # 40ms frames at 24kHz
        
    async def stream_audio_opus(
        self,
        audio_generator: AsyncGenerator[np.ndarray, None]
    ) -> AsyncGenerator[dict, None]:
        """
        Convert PCM audio stream to Opus-encoded base64 chunks
        
        Yields:
            {"type": "audio.delta", "delta": "base64_opus_chunk"}
        """
        buffer = np.array([], dtype=np.int16)
        
        async for audio_chunk in audio_generator:
            # Ensure int16
            if audio_chunk.dtype != np.int16:
                audio_chunk = (audio_chunk * 32767).astype(np.int16)
            
            # Add to buffer
            buffer = np.concatenate([buffer, audio_chunk])
            
            # Encode complete frames
            while len(buffer) >= self.frame_size:
                frame = buffer[:self.frame_size]
                buffer = buffer[self.frame_size:]
                
                # Encode to Opus
                opus_bytes = await asyncio.to_thread(
                    self.encoder.encode,
                    frame.tobytes(),
                    self.frame_size
                )
                
                # Base64 encode
                base64_opus = base64.b64encode(opus_bytes).decode('utf-8')
                
                yield {
                    "type": "audio.delta",
                    "delta": base64_opus,
                    "format": "opus"
                }
        
        # Flush remaining buffer
        if len(buffer) > 0:
            # Pad to frame size
            padded = np.pad(buffer, (0, self.frame_size - len(buffer)))
            opus_bytes = await asyncio.to_thread(
                self.encoder.encode,
                padded.tobytes(),
                self.frame_size
            )
            base64_opus = base64.b64encode(opus_bytes).decode('utf-8')
            yield {
                "type": "audio.delta",
                "delta": base64_opus,
                "format": "opus"
            }
```

### Handler Pattern (Option B)

```python
# core/realtime_handler.py

class KrellRealtimeHandler:
    """
    Orchestrates real-time voice conversation flow.
    
    Manages:
    - STT WebSocket connection
    - TTS generation
    - LLM interaction
    - Event queuing
    """
    
    def __init__(self, stt_url: str, tts_service, agent):
        self.stt_url = stt_url
        self.tts_service = tts_service
        self.agent = agent
        
        self.event_queue = asyncio.Queue()
        self.stt_ws = None
        self.transcription_buffer = []
        
    async def __aenter__(self):
        # Connect to STT service
        self.stt_ws = await websockets.connect(self.stt_url)
        return self
        
    async def __aexit__(self, *args):
        if self.stt_ws:
            await self.stt_ws.close()
    
    async def receive(self, audio_chunk: tuple[int, np.ndarray]):
        """Process incoming audio from user"""
        sample_rate, pcm_data = audio_chunk
        
        # Send to STT
        await self.stt_ws.send(pcm_data.tobytes())
        
        # Receive transcription (non-blocking)
        try:
            response = await asyncio.wait_for(
                self.stt_ws.recv(),
                timeout=0.01
            )
            data = json.loads(response)
            
            if data.get("type") == "transcription":
                self.transcription_buffer.append(data["text"])
                
            elif data.get("type") == "end_of_speech":
                # User finished speaking - trigger LLM
                await self._generate_response()
                
        except asyncio.TimeoutError:
            pass  # No transcription ready yet
    
    async def emit(self) -> Optional[dict]:
        """Get next event to send to client"""
        try:
            return self.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None
    
    async def _generate_response(self):
        """Generate and queue LLM response with TTS"""
        user_text = " ".join(self.transcription_buffer)
        self.transcription_buffer.clear()
        
        # Queue transcription event
        await self.event_queue.put({
            "type": "transcription.complete",
            "text": user_text
        })
        
        # Stream LLM response
        async for event in self.agent.chat_stream(None, user_text):
            if event["type"] == "text":
                # Queue text event
                await self.event_queue.put(event)
                
                # Generate TTS and queue audio
                audio, rate = await self.tts_service.synthesize_async(
                    event["content"]
                )
                await self.event_queue.put({
                    "type": "audio.delta",
                    "audio": audio,  # Will be Opus-encoded in emit_loop
                    "sample_rate": rate
                })
```

## Performance Considerations

### GPU Memory

Unmute's services:
- **STT**: ~2.5 GB VRAM (Kyutai)
- **TTS**: ~5.3 GB VRAM (Kyutai)
- **LLM**: ~6.1 GB VRAM (Mistral Small 24B)

**Total**: ~14 GB VRAM for all three on same GPU

For Krell:
- Keep LLM on main GPU
- Run TTS on same GPU (you already do this)
- STT can run on CPU (Whisper) or separate GPU

### Latency Breakdown

Unmute achieves ~450ms TTS latency on their production setup:
- STT: ~50ms (streaming)
- LLM: ~200ms (to first token)
- TTS: ~200ms (first sentence)

Current Krell could achieve similar by:
- Using streaming TTS (you already have this!)
- Minimizing LLM first-token latency
- Using Opus instead of WAV (smaller payloads)

## Conclusion

Unmute's architecture is **production-grade and well-designed**. Key takeaways:

1. **Dual-loop pattern** is elegant for bidirectional streaming
2. **Opus codec** is the right choice for real-time voice
3. **Handler pattern** cleanly separates concerns
4. **OpenAI Realtime API** provides a standard protocol

For Krell, I recommend **Option B (Hybrid)**:
- Keep existing text chat
- Add parallel voice mode
- Use Whisper for STT (simpler than Kyutai)
- Keep your excellent TTS streaming
- Consider Opus for efficiency

This gives you voice support without a complete rewrite!
