# Voice Input Quickstart for Krell

This guide shows you how to add voice input to Krell with minimal code changes, inspired by Unmute.

## Quick Implementation (1-2 hours)

### Step 1: Install Whisper

```bash
pip install faster-whisper
# OR for CUDA support
pip install faster-whisper[cuda]
```

### Step 2: Add Transcription Endpoint

Create `api/voice.py`:

```python
"""Voice input support using Whisper STT"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from faster_whisper import WhisperModel
import tempfile
import os
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()

# Global model instance
_whisper_model: Optional[WhisperModel] = None


def get_whisper_model() -> WhisperModel:
    """Get or create Whisper model instance"""
    global _whisper_model
    
    if _whisper_model is None:
        logger.info("Loading Whisper model...")
        # Use "base" for speed, "small" or "medium" for accuracy
        _whisper_model = WhisperModel(
            "base",
            device="cuda",  # or "cpu"
            compute_type="float16"  # or "int8" for CPU
        )
        logger.info("Whisper model loaded")
    
    return _whisper_model


@router.post("/api/voice/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str = "en"
):
    """
    Transcribe audio file to text using Whisper.
    
    Accepts: WAV, MP3, M4A, WEBM, or any ffmpeg-supported format
    Returns: {"text": "transcribed text", "language": "detected_language"}
    """
    if not audio.filename:
        raise HTTPException(400, "No file provided")
    
    # Save uploaded file to temp location
    suffix = os.path.splitext(audio.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        logger.info(f"Transcribing audio file: {audio.filename} ({len(content)} bytes)")
        
        # Transcribe in thread pool (Whisper is CPU/GPU intensive)
        model = get_whisper_model()
        segments, info = await asyncio.to_thread(
            model.transcribe,
            tmp_path,
            language=language if language != "auto" else None,
            beam_size=5
        )
        
        # Combine all segments
        text = " ".join([seg.text for seg in segments])
        
        logger.info(f"Transcription: {text[:100]}...")
        
        return {
            "text": text.strip(),
            "language": info.language,
            "duration": info.duration
        }
    
    except Exception as e:
        logger.error(f"Transcription error: {e}", exc_info=True)
        raise HTTPException(500, f"Transcription failed: {str(e)}")
    
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except:
            pass


@router.post("/api/voice/transcribe-stream")
async def transcribe_audio_stream(
    audio: UploadFile = File(...),
    language: str = "en"
):
    """
    Transcribe with word-level timestamps.
    
    Returns streaming response with each word as it's detected.
    Useful for real-time transcription display.
    """
    suffix = os.path.splitext(audio.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        model = get_whisper_model()
        
        # Get segments with word timestamps
        segments, info = await asyncio.to_thread(
            model.transcribe,
            tmp_path,
            language=language if language != "auto" else None,
            word_timestamps=True
        )
        
        words = []
        for segment in segments:
            if hasattr(segment, 'words') and segment.words:
                for word in segment.words:
                    words.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "probability": word.probability
                    })
        
        full_text = " ".join([w["word"] for w in words])
        
        return {
            "text": full_text,
            "words": words,
            "language": info.language
        }
    
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass
```

### Step 3: Register Voice Router

Edit `main.py`:

```python
from api import voice

# Add voice router
app.include_router(voice.router, tags=["voice"])
```

### Step 4: Frontend Integration

Add to your frontend (example with vanilla JS):

```javascript
// Record audio from microphone
class VoiceRecorder {
  constructor() {
    this.mediaRecorder = null;
    this.audioChunks = [];
  }

  async startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true
      } 
    });
    
    this.mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'audio/webm;codecs=opus'
    });
    
    this.audioChunks = [];
    
    this.mediaRecorder.ondataavailable = (event) => {
      this.audioChunks.push(event.data);
    };
    
    this.mediaRecorder.start();
    console.log('Recording started');
  }

  async stopRecording() {
    return new Promise((resolve) => {
      this.mediaRecorder.onstop = () => {
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        resolve(audioBlob);
      };
      
      this.mediaRecorder.stop();
      this.mediaRecorder.stream.getTracks().forEach(track => track.stop());
    });
  }

  async transcribeAudio(audioBlob) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('language', 'en');
    
    const response = await fetch('/api/voice/transcribe', {
      method: 'POST',
      body: formData
    });
    
    const data = await response.json();
    return data.text;
  }
}

// Usage
const recorder = new VoiceRecorder();

// Start recording on button press
document.getElementById('recordBtn').addEventListener('mousedown', async () => {
  await recorder.startRecording();
});

// Stop and transcribe on button release
document.getElementById('recordBtn').addEventListener('mouseup', async () => {
  const audioBlob = await recorder.stopRecording();
  const text = await recorder.transcribeAudio(audioBlob);
  
  // Insert transcription into chat input
  document.getElementById('chatInput').value = text;
  
  // Optionally auto-send
  // sendMessage(text);
});
```

### Step 5: Test It

```bash
# Start Krell
python main.py

# In browser console:
# 1. Click record button
# 2. Speak: "Hello Krell, what's the weather today?"
# 3. Release button
# 4. See transcription appear in chat input
```

## Advanced: WebSocket Voice Streaming

For lower latency, stream audio chunks as you record:

```python
# api/voice.py - Add WebSocket endpoint

import numpy as np
import io
from pydub import AudioSegment

@router.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    """
    Real-time voice transcription over WebSocket.
    
    Client sends: Binary audio chunks (16kHz, 16-bit PCM)
    Server sends: {"type": "transcription", "text": "..."}
    """
    await websocket.accept()
    
    # Buffer for accumulating audio
    audio_buffer = io.BytesIO()
    model = get_whisper_model()
    
    try:
        while True:
            # Receive audio chunk
            data = await websocket.receive_bytes()
            audio_buffer.write(data)
            
            # Transcribe when we have enough audio (~3 seconds)
            if audio_buffer.tell() >= 16000 * 2 * 3:  # 3 seconds at 16kHz, 16-bit
                audio_buffer.seek(0)
                
                # Save to temp file
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    # Write WAV header
                    import wave
                    with wave.open(tmp.name, 'wb') as wav:
                        wav.setnchannels(1)
                        wav.setsampwidth(2)
                        wav.setframerate(16000)
                        wav.writeframes(audio_buffer.read())
                    
                    # Transcribe
                    segments, _ = await asyncio.to_thread(
                        model.transcribe,
                        tmp.name,
                        language="en"
                    )
                    
                    text = " ".join([seg.text for seg in segments])
                    
                    # Send transcription
                    await websocket.send_json({
                        "type": "transcription",
                        "text": text
                    })
                    
                    # Clean up
                    os.unlink(tmp.name)
                
                # Reset buffer
                audio_buffer = io.BytesIO()
    
    except WebSocketDisconnect:
        logger.info("Voice WebSocket disconnected")
```

Frontend for streaming:

```javascript
class StreamingVoiceRecorder {
  constructor(websocketUrl) {
    this.ws = new WebSocket(websocketUrl);
    this.audioContext = new AudioContext({ sampleRate: 16000 });
    this.processor = null;
  }

  async startStreaming() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const source = this.audioContext.createMediaStreamSource(stream);
    
    // Use ScriptProcessorNode for audio processing
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
    
    this.processor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0);
      
      // Convert float32 to int16
      const int16Data = new Int16Array(inputData.length);
      for (let i = 0; i < inputData.length; i++) {
        const s = Math.max(-1, Math.min(1, inputData[i]));
        int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      
      // Send to WebSocket
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(int16Data.buffer);
      }
    };
    
    source.connect(this.processor);
    this.processor.connect(this.audioContext.destination);
    
    // Listen for transcriptions
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'transcription') {
        console.log('Transcription:', data.text);
        this.onTranscription(data.text);
      }
    };
  }

  stopStreaming() {
    if (this.processor) {
      this.processor.disconnect();
    }
    this.ws.close();
  }

  onTranscription(text) {
    // Override this in your app
    console.log('Received:', text);
  }
}
```

## Performance Tips

### 1. Model Selection

```python
# For different use cases:

# Fast (< 1 second on GPU)
WhisperModel("tiny", device="cuda")

# Balanced (1-2 seconds on GPU) - RECOMMENDED
WhisperModel("base", device="cuda")

# Accurate (3-5 seconds on GPU)
WhisperModel("small", device="cuda")

# Best quality (8-10 seconds on GPU)
WhisperModel("medium", device="cuda")
```

### 2. GPU Memory

Whisper models memory usage:
- tiny: ~1 GB
- base: ~1 GB
- small: ~2 GB
- medium: ~5 GB
- large: ~10 GB

You can run Whisper on the same GPU as your TTS!

### 3. Batch Processing

For multiple files:

```python
async def transcribe_batch(file_paths: list[str]):
    model = get_whisper_model()
    
    # Process in parallel (limit to avoid OOM)
    semaphore = asyncio.Semaphore(3)
    
    async def transcribe_one(path):
        async with semaphore:
            segments, _ = await asyncio.to_thread(
                model.transcribe, path
            )
            return " ".join([seg.text for seg in segments])
    
    tasks = [transcribe_one(p) for p in file_paths]
    return await asyncio.gather(*tasks)
```

## Integration with Existing Krell Chat

Modify `api/websocket.py`:

```python
async def handle_message(websocket, session_id, data):
    msg_type = data.get("type")
    
    # ADD THIS:
    if msg_type == "voice":
        # Receive audio, transcribe, process as message
        audio_base64 = data.get("audio")
        audio_bytes = base64.b64decode(audio_base64)
        
        # Transcribe
        text = await transcribe_audio_bytes(audio_bytes)
        
        # Send transcription to client
        await websocket.send_json({
            "type": "transcription",
            "text": text
        })
        
        # Process as normal text message
        await handle_chat_message(
            websocket=websocket,
            session_id=session_id,
            content=text,
            conversation_id=data.get("conversation_id")
        )
    
    elif msg_type == "message":
        # Existing text message handling
        ...

async def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """Helper to transcribe audio from bytes"""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    
    try:
        from api.voice import get_whisper_model
        model = get_whisper_model()
        
        segments, _ = await asyncio.to_thread(
            model.transcribe, tmp_path
        )
        
        return " ".join([seg.text for seg in segments])
    finally:
        os.unlink(tmp_path)
```

## Testing

Create `tests/test_voice.py`:

```python
import pytest
from fastapi.testclient import TestClient
from main import app
import io
import wave

client = TestClient(app)

def create_test_audio():
    """Create a 1-second silent WAV file for testing"""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\x00' * 32000)
    
    buffer.seek(0)
    return buffer

def test_transcribe_endpoint():
    audio = create_test_audio()
    
    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("test.wav", audio, "audio/wav")}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "text" in data
    assert "language" in data

def test_transcribe_with_language():
    audio = create_test_audio()
    
    response = client.post(
        "/api/voice/transcribe",
        files={"audio": ("test.wav", audio, "audio/wav")},
        data={"language": "es"}
    )
    
    assert response.status_code == 200
```

## Next Steps

Once voice input works:

1. **Add push-to-talk UI**: Hold space bar to record
2. **Add voice activity detection**: Auto-detect when user stops speaking
3. **Add real-time transcription display**: Show words as they're transcribed
4. **Support multiple languages**: Let users choose input language
5. **Add wake word detection**: "Hey Krell..."

For full Unmute-style real-time voice:
- See `docs/UNMUTE_INTEGRATION_GUIDE.md`
- Implement Opus streaming
- Add continuous STT
- Support voice interruptions

## Troubleshooting

### "Model not found" error
```bash
# Models are downloaded to ~/.cache/huggingface/
# Ensure you have internet and disk space
ls ~/.cache/huggingface/hub/
```

### GPU out of memory
```python
# Use smaller model or CPU
WhisperModel("tiny", device="cpu")
```

### Poor transcription quality
```python
# Use larger model
WhisperModel("small", device="cuda")

# Or increase beam size (slower but better)
model.transcribe(path, beam_size=10)
```

### Audio format issues
```bash
# Install ffmpeg for format conversion
sudo apt install ffmpeg  # Ubuntu
brew install ffmpeg      # Mac
```

Whisper supports any format ffmpeg can read!
