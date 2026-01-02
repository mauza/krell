"""
WebSocket API for real-time chat with streaming text and audio.

Provides bidirectional communication for chat messages with lower latency
than HTTP endpoints.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Optional, Dict
import uuid
import json
import logging
import asyncio

from config import Config

logger = logging.getLogger(__name__)

router = APIRouter()
config = Config()


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        # Track ongoing generations for cancellation
        self.active_generations: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: {session_id}")

    def disconnect(self, session_id: str):
        """Unregister a WebSocket connection."""
        self.active_connections.pop(session_id, None)
        # Cancel any active generation
        if session_id in self.active_generations:
            task = self.active_generations.pop(session_id)
            task.cancel()
        logger.info(f"WebSocket disconnected: {session_id}")

    async def send_json(self, session_id: str, data: dict):
        """Send JSON message to a specific session."""
        if ws := self.active_connections.get(session_id):
            try:
                await ws.send_json(data)
            except Exception as e:
                logger.error(f"Error sending JSON to {session_id}: {e}")
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


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat.

    Protocol:
    - Client sends: {"type": "message", "content": "...", "conversation_id": "..."}
    - Client sends: {"type": "cancel"}
    - Client sends: {"type": "ping"}
    - Server sends: JSON events (conversation_id, text, tool_call, etc.)
    - Server sends: Binary audio chunks
    """
    session_id = str(uuid.uuid4())
    await manager.connect(websocket, session_id)

    try:
        # Send connection confirmation
        await websocket.send_json({"type": "connected", "session_id": session_id})

        # Listen for messages
        while True:
            data = await websocket.receive_json()
            await handle_message(websocket, session_id, data)

    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        logger.error(f"WebSocket error for {session_id}: {e}", exc_info=True)
        manager.disconnect(session_id)


async def handle_message(websocket: WebSocket, session_id: str, data: dict):
    """Handle incoming WebSocket messages."""
    msg_type = data.get("type")

    if msg_type == "ping":
        await websocket.send_json({"type": "pong"})

    elif msg_type == "cancel":
        # Cancel any in-progress generation
        if session_id in manager.active_generations:
            task = manager.active_generations[session_id]
            task.cancel()
            manager.unregister_generation(session_id)
            logger.info(f"Cancelled generation for session {session_id}")

    elif msg_type == "message":
        # Handle chat message
        await handle_chat_message(
            websocket=websocket,
            session_id=session_id,
            content=data.get("content", ""),
            conversation_id=data.get("conversation_id"),
        )

    else:
        logger.warning(f"Unknown message type: {msg_type}")


async def handle_chat_message(
    websocket: WebSocket,
    session_id: str,
    content: str,
    conversation_id: Optional[str],
):
    """
    Handle a chat message with streaming response and TTS.

    Streams:
    1. conversation_id event
    2. text chunks as they're generated
    3. tool_call and tool_result events
    4. audio_start event
    5. binary audio chunks
    6. audio_end event
    7. done event
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
