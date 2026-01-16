"""
WebSocket API for real-time chat with streaming text and audio.

Provides bidirectional communication for chat messages with lower latency
than HTTP endpoints.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional, Dict, Union
import uuid
import json
import logging
import asyncio
import time

from config import Config
from api.websocket_protocol import (
    WebSocketProtocol,
    TimingTracker,
    get_event_loop_time,
    MessageTypes,
    AudioFrameMessage,
    default_protocol,
)

logger = logging.getLogger(__name__)

router = APIRouter()
config = Config()


class ConnectionManager:
    """Manages active WebSocket connections with protocol support."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.protocols: Dict[str, WebSocketProtocol] = {}
        # Track ongoing generations for cancellation
        self.active_generations: Dict[str, asyncio.Task] = {}
        # Timing trackers for each session
        self.timing_trackers: Dict[str, TimingTracker] = {}

    async def connect(
        self, websocket: WebSocket, session_id: str, use_msgpack: bool = True
    ):
        """Accept and register a new WebSocket connection with protocol."""
        # Disable compression for lower latency
        await websocket.accept(subprotocol="msgpack" if use_msgpack else None)
        self.active_connections[session_id] = websocket
        self.protocols[session_id] = WebSocketProtocol(
            use_msgpack=use_msgpack,
            compress=False,  # Disable compression for lower latency
        )
        self.timing_trackers[session_id] = TimingTracker()
        logger.info(f"WebSocket connected: {session_id} (msgpack: {use_msgpack})")

    def disconnect(self, session_id: str):
        """Unregister a WebSocket connection."""
        self.active_connections.pop(session_id, None)
        self.protocols.pop(session_id, None)
        self.timing_trackers.pop(session_id, None)
        # Cancel any active generation
        if session_id in self.active_generations:
            task = self.active_generations.pop(session_id)
            task.cancel()
        logger.info(f"WebSocket disconnected: {session_id}")

    async def send_message(self, session_id: str, data: dict):
        """Send message using appropriate protocol (msgpack or JSON)."""
        if ws := self.active_connections.get(session_id):
            try:
                protocol = self.protocols.get(session_id, default_protocol)
                encoded = protocol.encode(data)

                if isinstance(encoded, bytes):
                    await ws.send_bytes(encoded)
                else:
                    await ws.send_text(encoded)
            except Exception as e:
                logger.error(f"Error sending message to {session_id}: {e}")
                self.disconnect(session_id)

    async def send_bytes(self, session_id: str, data: bytes):
        """Send binary message to a specific session."""
        if ws := self.active_connections.get(session_id):
            try:
                await ws.send_bytes(data)
            except Exception as e:
                logger.error(f"Error sending bytes to {session_id}: {e}")
                self.disconnect(session_id)

    def register_generation(self, session_id: str, task: asyncio.Task):
        """Register an active generation task for potential cancellation."""
        self.active_generations[session_id] = task

    def unregister_generation(self, session_id: str):
        """Unregister a completed generation task."""
        self.active_generations.pop(session_id, None)

    def get_protocol(self, session_id: str) -> WebSocketProtocol:
        """Get protocol for a session."""
        return self.protocols.get(session_id, default_protocol)

    def get_timing_tracker(self, session_id: str) -> TimingTracker:
        """Get timing tracker for a session."""
        return self.timing_trackers.get(session_id, TimingTracker())


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat with msgpack support.

    Protocol (backward compatible):
    - Client can send JSON or msgpack (auto-detected)
    - Server responds with same protocol client used
    - Client sends: {"type": "message", "content": "...", "conversation_id": "..."}
    - Client sends: {"type": "cancel"}
    - Client sends: {"type": "ping"}
    - Server sends: events (conversation_id, text, tool_call, etc.)
    - Server sends: Binary audio chunks or audio frames
    """
    session_id = str(uuid.uuid4())

    # Detect if client supports msgpack from WebSocket subprotocol
    client_subprotocols = websocket.headers.get("sec-websocket-protocol", "")
    use_msgpack = "msgpack" in client_subprotocols.lower()

    await manager.connect(websocket, session_id, use_msgpack=use_msgpack)

    try:
        # Send connection confirmation with protocol info
        await manager.send_message(
            session_id,
            {
                "type": MessageTypes.CONNECTED,
                "session_id": session_id,
                "protocol": "msgpack" if use_msgpack else "json",
                "timestamp": time.time(),
            },
        )

        # Listen for messages
        while True:
            # Receive message (auto-detect format)
            message = await websocket.receive()

            # Handle different message types
            if message["type"] == "websocket.receive":
                data = message.get("text") or message.get("bytes")
                if data:
                    await handle_raw_message(websocket, session_id, data)

            elif message["type"] == "websocket.disconnect":
                break

    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket error for {session_id}: {e}", exc_info=True)
        manager.disconnect(session_id)


async def handle_raw_message(
    websocket: WebSocket, session_id: str, raw_data: Union[str, bytes]
):
    """Handle raw WebSocket message, auto-detecting format."""
    protocol = manager.get_protocol(session_id)
    data = protocol.decode(raw_data)

    if data is None:
        logger.warning(f"Failed to decode message for session {session_id}")
        return

    # Add timing metadata
    data = protocol.add_timing_metadata(data, "receive")

    await handle_message(websocket, session_id, data)


async def handle_message(websocket: WebSocket, session_id: str, data: dict):
    """Handle incoming WebSocket messages."""
    msg_type = data.get("type")
    protocol = manager.get_protocol(session_id)
    timing_tracker = manager.get_timing_tracker(session_id)

    if msg_type == MessageTypes.PING:
        timing_tracker.start_stage("ping_response")
        await manager.send_message(
            session_id, {"type": MessageTypes.PONG, "timestamp": time.time()}
        )
        timing_tracker.end_stage("ping_response")

    elif msg_type == MessageTypes.CANCEL:
        # Cancel any in-progress generation
        timing_tracker.start_stage("cancel")
        if session_id in manager.active_generations:
            task = manager.active_generations[session_id]
            task.cancel()
            manager.unregister_generation(session_id)
            logger.info(f"Cancelled generation for session {session_id}")
        timing_tracker.end_stage("cancel")

    elif msg_type == MessageTypes.MESSAGE:
        # Handle chat message with timing
        timing_tracker.start_stage("message_processing")
        await handle_chat_message(
            websocket=websocket,
            session_id=session_id,
            content=data.get("content", ""),
            conversation_id=data.get("conversation_id"),
            timing_tracker=timing_tracker,
        )
        timing_tracker.end_stage("message_processing")

    else:
        logger.warning(f"Unknown message type: {msg_type}")
        await manager.send_message(
            session_id,
            {
                "type": MessageTypes.ERROR,
                "message": f"Unknown message type: {msg_type}",
                "code": "UNKNOWN_MESSAGE_TYPE",
            },
        )


async def handle_chat_message(
    websocket: WebSocket,
    session_id: str,
    content: str,
    conversation_id: Optional[str],
    timing_tracker: TimingTracker,
):
    """
    Handle a chat message with streaming response and TTS.

    Streams:
    1. conversation_id event
    2. text chunks as they're generated
    3. tool_call and tool_result events
    4. audio_start event
    5. binary audio chunks or audio frames
    6. audio_end event
    7. done event with timing metrics
    """
    from api.routes import get_krell_agent, tts_service

    try:
        agent = await get_krell_agent()

        if not agent:
            raise RuntimeError("Failed to initialize agent")

        # Create task for generation (can be cancelled)
        async def generate():
            full_text = []
            current_conversation_id = conversation_id

            try:
                # Stream text from agent
                async for event in agent.chat_stream(conversation_id, content):
                    if event["type"] == "conversation_id":
                        current_conversation_id = event["conversation_id"]
                        await websocket.send_json(
                            {
                                "type": "conversation_id",
                                "conversation_id": current_conversation_id,
                            }
                        )

                    elif event["type"] == "text":
                        full_text.append(event["content"])
                        await websocket.send_json(
                            {"type": "text", "content": event["content"]}
                        )

                    elif event["type"] == "tool_call":
                        await websocket.send_json(
                            {
                                "type": "tool_call",
                                "id": event["id"],
                                "name": event["name"],
                                "input": event["input"],
                            }
                        )

                    elif event["type"] == "tool_result":
                        await websocket.send_json(
                            {
                                "type": "tool_result",
                                "id": event.get("tool_use_id"),
                                "content": event["content"],
                            }
                        )

                # Generate and stream TTS audio
                response_text = "".join(full_text)
                logger.info(
                    f"[CHAT] Calling TTS with response_text length: {len(response_text)}"
                )
                await stream_tts_over_websocket(websocket, response_text)

                # Send completion
                await websocket.send_json(
                    {
                        "type": "done",
                        "full_text": response_text,
                        "conversation_id": current_conversation_id,
                    }
                )

            except asyncio.CancelledError:
                logger.info(f"Generation cancelled for session {session_id}")
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Generation cancelled",
                        "code": "CANCELLED",
                    }
                )
                raise

        # Create and track the generation task
        task = asyncio.create_task(generate())
        manager.register_generation(session_id, task)

        try:
            await task
        finally:
            manager.unregister_generation(session_id)

    except asyncio.CancelledError:
        # Already handled in generate()
        pass
    except Exception as e:
        logger.error(f"Error in chat message handler: {e}", exc_info=True)
        await websocket.send_json(
            {
                "type": "error",
                "message": str(e),
                "code": "PROCESSING_ERROR",
            }
        )


async def stream_tts_over_websocket(websocket: WebSocket, text: str):
    """
    Stream TTS audio over WebSocket as binary frames.

    Generates audio per-sentence and sends each as a complete WAV file
    for lower latency playback.

    Sends:
    1. audio_start JSON event
    2. Binary WAV data (one complete WAV per sentence)
    3. audio_end JSON event
    """
    from api.routes import tts_service
    from services.tts import chunk_text_by_sentences
    import io
    import wave
    import numpy as np

    try:
        logger.info(
            f"[TTS] stream_tts_over_websocket called with text length: {len(text) if text else 0}"
        )

        if not text or not text.strip():
            logger.warning("[TTS] Empty text, skipping TTS")
            return

        if not tts_service._kyutai_model:
            logger.error("[TTS] Kyutai model not initialized")
            return

        logger.info(f"[TTS] Kyutai model device: {tts_service._kyutai_model.device}")

        # Send audio start event
        await websocket.send_json({"type": "audio_start", "format": "wav"})

        # Split into sentences
        sentences = chunk_text_by_sentences(text, max_length=200)
        logger.info(f"Generating TTS for {len(sentences)} sentences")

        # Generate and send audio for each sentence
        for i, sentence in enumerate(sentences):
            logger.info(f"TTS sentence {i + 1}/{len(sentences)}: {sentence[:40]}...")

            # Get configured voice (check database first, fallback to config)
            from database.db import Database

            database = Database(config.database_path)
            configured_voice = (
                await database.get_setting("tts_voice") or config.tts_voice
            )

            # Generate audio for this sentence
            audio_array, sample_rate = await asyncio.to_thread(
                tts_service._kyutai_model.synthesize,
                text=sentence,
                voice=configured_voice,
                speed=config.tts_speed,
                lang=config.tts_lang,
            )

            # Convert to int16
            if audio_array.dtype != np.int16:
                if audio_array.dtype in [np.float32, np.float64]:
                    audio_array = np.clip(audio_array, -1.0, 1.0)
                    audio_array = (audio_array * 32767).astype(np.int16)
                else:
                    audio_array = audio_array.astype(np.int16)

            # Create complete WAV file for this sentence
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_array.tobytes())

            # Send complete WAV immediately
            wav_data = wav_buffer.getvalue()
            await websocket.send_bytes(wav_data)
            logger.info(f"Sent sentence {i + 1} audio: {len(wav_data)} bytes")

        # Send audio end event
        await websocket.send_json({"type": "audio_end"})

    except Exception as e:
        logger.error(f"Error streaming TTS: {e}", exc_info=True)
        await websocket.send_json(
            {"type": "error", "message": f"TTS error: {str(e)}", "code": "TTS_ERROR"}
        )
