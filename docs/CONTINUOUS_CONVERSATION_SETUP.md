# Continuous Conversation Mode - Setup Guide

This guide shows you how to set up and use Krell's continuous voice conversation mode, inspired by Unmute's architecture.

## Architecture Overview

Krell's realtime mode uses:
- **Dual-loop WebSocket** pattern (like Unmute)
- **Opus audio codec** for efficient streaming
- **faster-whisper** for Speech-to-Text (STT)
- **Kyutai TTS** for Text-to-Speech (already configured)
- **Voice Activity Detection** (VAD) to detect speech start/end
- **OpenAI Realtime API** compatible protocol

```
Browser → Opus audio → WebSocket → STT → LLM → TTS → Opus audio → Browser
         (receive_loop)                                   (emit_loop)
```

## Installation

### 1. Install Required Dependencies

```bash
# Install opuslib for Opus codec (requires system libopus)
# On Ubuntu/Debian:
sudo apt-get install libopus0 libopus-dev

# On macOS:
brew install opus

# Then install Python package:
pip install opuslib

# Install faster-whisper for STT
pip install faster-whisper

# Verify installation
python -c "import opuslib; import faster_whisper; print('All dependencies installed!')"
```

### 2. Update Krell

The code has been added to your project:
- `api/realtime.py` - WebSocket endpoint with dual loops
- `api/realtime_events.py` - OpenAI Realtime API event schemas
- `core/realtime_handler.py` - Main handler orchestrating STT→LLM→TTS
- `services/stt.py` - Speech-to-Text service
- `services/opus_audio.py` - Opus codec support

### 3. Start Krell

```bash
python main.py
```

Check the logs for:
```
INFO:main:Krell backend started successfully!
INFO:api.realtime:Realtime API endpoint available at /v1/realtime
```

### 4. Test Health Endpoint

```bash
curl http://localhost:8000/v1/realtime/health
```

Should return:
```json
{
  "status": "healthy",
  "tts_ready": true,
  "stt_ready": true,
  "available_slots": 4,
  "max_concurrent_sessions": 4
}
```

## Frontend Integration

### Basic Example (Vanilla JavaScript)

```html
<!DOCTYPE html>
<html>
<head>
    <title>Krell Voice Chat</title>
</head>
<body>
    <h1>Krell Continuous Conversation</h1>
    
    <div id="status">Disconnected</div>
    <button id="connectBtn">Connect</button>
    
    <div id="transcription" style="margin-top: 20px;">
        <h3>You said:</h3>
        <p id="userText"></p>
    </div>
    
    <div id="response">
        <h3>Krell:</h3>
        <p id="aiText"></p>
    </div>
    
    <script src="krell-voice.js"></script>
</body>
</html>
```

```javascript
// krell-voice.js

class KrellVoiceChat {
    constructor(serverUrl) {
        this.serverUrl = serverUrl;
        this.ws = null;
        this.audioContext = null;
        this.mediaStream = null;
        this.processor = null;
        this.audioQueue = [];
        this.isPlaying = false;
        
        // Opus encoder/decoder (browser native)
        this.mediaRecorder = null;
    }
    
    async connect() {
        // Connect to WebSocket
        this.ws = new WebSocket(this.serverUrl);
        this.ws.onopen = () => this.onConnected();
        this.ws.onmessage = (event) => this.onMessage(event);
        this.ws.onerror = (error) => console.error('WebSocket error:', error);
        this.ws.onclose = () => this.onDisconnected();
    }
    
    async onConnected() {
        console.log('Connected to Krell');
        document.getElementById('status').textContent = 'Connected';
        
        // Initialize audio
        await this.initializeAudio();
        
        // Start recording
        await this.startRecording();
    }
    
    async initializeAudio() {
        // Create audio context
        this.audioContext = new AudioContext({ sampleRate: 24000 });
        
        // Get microphone access
        this.mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                sampleRate: 24000,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            }
        });
        
        console.log('Audio initialized');
    }
    
    async startRecording() {
        // Use MediaRecorder with Opus codec
        this.mediaRecorder = new MediaRecorder(this.mediaStream, {
            mimeType: 'audio/webm;codecs=opus',
            audioBitsPerSecond: 48000
        });
        
        this.mediaRecorder.ondataavailable = async (event) => {
            if (event.data.size > 0) {
                // Convert blob to base64
                const base64Audio = await this.blobToBase64(event.data);
                
                // Send to server
                this.ws.send(JSON.stringify({
                    type: 'input_audio_buffer.append',
                    audio: base64Audio
                }));
            }
        };
        
        // Record in small chunks for low latency
        this.mediaRecorder.start(100); // 100ms chunks
        
        console.log('Recording started');
    }
    
    async blobToBase64(blob) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64 = reader.result.split(',')[1];
                resolve(base64);
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    }
    
    async onMessage(event) {
        const data = JSON.parse(event.data);
        
        console.log('Received event:', data.type);
        
        switch (data.type) {
            case 'session.created':
                console.log('Session created:', data.session);
                break;
            
            case 'conversation.item.input_audio_transcription.completed':
                // User's speech was transcribed
                document.getElementById('userText').textContent = data.transcript;
                break;
            
            case 'response.text.delta':
                // AI is generating text
                const currentText = document.getElementById('aiText').textContent;
                document.getElementById('aiText').textContent = currentText + data.delta;
                break;
            
            case 'response.audio.delta':
                // AI audio chunk
                await this.playAudioChunk(data.delta);
                break;
            
            case 'response.done':
                console.log('Response complete');
                break;
            
            case 'error':
                console.error('Server error:', data.error);
                break;
        }
    }
    
    async playAudioChunk(base64Audio) {
        // Decode base64 to Opus
        const opusData = atob(base64Audio);
        const opusArray = new Uint8Array(opusData.length);
        for (let i = 0; i < opusData.length; i++) {
            opusArray[i] = opusData.charCodeAt(i);
        }
        
        // Create blob and decode with browser
        const blob = new Blob([opusArray], { type: 'audio/opus' });
        const arrayBuffer = await blob.arrayBuffer();
        
        // Decode audio
        try {
            const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
            
            // Play audio
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);
            source.start();
        } catch (e) {
            console.error('Error playing audio:', e);
        }
    }
    
    onDisconnected() {
        console.log('Disconnected from Krell');
        document.getElementById('status').textContent = 'Disconnected';
        
        // Stop recording
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        
        // Stop media stream
        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
        }
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
    }
}

// Initialize
let chat = null;

document.getElementById('connectBtn').addEventListener('click', async () => {
    if (chat && chat.ws && chat.ws.readyState === WebSocket.OPEN) {
        chat.disconnect();
        chat = null;
        document.getElementById('connectBtn').textContent = 'Connect';
    } else {
        chat = new KrellVoiceChat('ws://localhost:8000/v1/realtime');
        await chat.connect();
        document.getElementById('connectBtn').textContent = 'Disconnect';
    }
});
```

## Testing

### Test 1: Connection

1. Open the HTML file in your browser
2. Click "Connect"
3. Check browser console for: `"Connected to Krell"`
4. Check server logs for: `"New realtime connection"`

### Test 2: Speech Recognition

1. Connect and speak: "Hello Krell, how are you?"
2. Watch server logs for: `"Transcription: 'Hello Krell, how are you?'"`
3. See transcription appear on page

### Test 3: Full Conversation

1. Connect
2. Speak a question
3. Wait for AI to respond (you should hear audio)
4. Check that you can interrupt AI by speaking again

## Troubleshooting

### "opuslib not installed" error

```bash
# Make sure system libopus is installed first
sudo apt-get install libopus0 libopus-dev  # Ubuntu
brew install opus  # macOS

# Then install Python package
pip install opuslib
```

### "faster-whisper not installed" error

```bash
pip install faster-whisper

# For GPU support (optional but recommended):
pip install faster-whisper[cuda]
```

### No audio output

Check browser console for errors. Try:
```javascript
// Test audio playback
const audioContext = new AudioContext();
const oscillator = audioContext.createOscillator();
oscillator.connect(audioContext.destination);
oscillator.start();
setTimeout(() => oscillator.stop(), 1000);
```

### Echo/feedback problems

1. **Use headphones** - this eliminates most echo
2. Browser echo cancellation should handle speakers, but quality varies
3. Check that `echoCancellation: true` is set in `getUserMedia`

### GPU out of memory

Reduce max concurrent sessions in `api/realtime.py`:
```python
MAX_CONCURRENT_SESSIONS = 2  # Lower if needed
```

Or use smaller Whisper model:
```python
stt_service = STTService(
    model_size="tiny",  # Smaller, faster, less accurate
    device="cpu"  # Use CPU instead of GPU
)
```

## Configuration

### Adjust VAD Sensitivity

In `services/stt.py`, modify `SimpleVAD`:

```python
self.vad = SimpleVAD(
    sample_rate=SAMPLE_RATE,
    energy_threshold=0.005,  # Lower = more sensitive
    silence_frames_required=10  # Lower = faster end-of-speech detection
)
```

### Change Whisper Model

Larger models are more accurate but slower:
- `tiny` - Fastest, least accurate (~1 GB VRAM)
- `base` - Good balance (~1 GB VRAM) **← DEFAULT**
- `small` - Better quality (~2 GB VRAM)
- `medium` - High quality (~5 GB VRAM)
- `large` - Best quality (~10 GB VRAM)

Update in `api/realtime.py`:
```python
stt_service = STTService(
    model_size="small",  # Change here
    device="cuda",
    compute_type="float16"
)
```

### Adjust Session Limits

Control concurrent connections in `api/realtime.py`:
```python
MAX_CONCURRENT_SESSIONS = 4  # Adjust based on your GPU
```

## Performance Metrics

Expected latency breakdown:
- STT (Whisper base): ~100-200ms
- LLM first token: ~200-500ms (depends on model)
- TTS (Kyutai): ~200-400ms
- Network: ~50-100ms

**Total**: ~600-1200ms from end of speech to start of audio playback

This is comparable to Unmute's ~450ms on their production setup!

## Advanced: Interruption Support

The system supports interrupting the AI mid-speech:

```javascript
// User starts speaking while AI is talking
// The handler automatically:
// 1. Detects speech via VAD
// 2. Stops TTS generation
// 3. Clears audio queue
// 4. Starts processing new user input

// No special code needed - it just works!
```

## Next Steps

1. **Improve frontend**: Add visual feedback, waveforms, status indicators
2. **Add wake word**: Detect "Hey Krell" to start listening
3. **Multi-language**: Support other languages in STT
4. **Better VAD**: Use WebRTC VAD or Silero VAD for better speech detection
5. **Production deployment**: Add authentication, rate limiting, monitoring

## Architecture Comparison

| Feature | Krell | Unmute |
|---------|-------|--------|
| STT | faster-whisper (Whisper) | Kyutai STT |
| TTS | Kyutai | Kyutai |
| LLM | Any OpenAI-compatible | Any OpenAI-compatible |
| Audio Codec | Opus | Opus |
| Protocol | OpenAI Realtime API | OpenAI Realtime API |
| WebSocket Pattern | Dual-loop | Dual-loop |
| VAD | Simple energy-based | Advanced Kyutai VAD |
| Deployment | Single server | Multi-service (Docker) |

## Summary

You now have a fully functional continuous conversation system! 

Key features:
- ✅ Real-time voice input
- ✅ Streaming LLM responses
- ✅ Real-time voice output
- ✅ Interruption support
- ✅ Low latency (~600-1200ms)
- ✅ OpenAI Realtime API compatible

Enjoy your voice-powered AI assistant! 🎤🤖
