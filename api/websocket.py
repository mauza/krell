"""
WebSocket API for real-time chat with streaming text and audio.

This module provides bidirectional communication for chat with:
- OpenAI Realtime API-compatible typed events
- Conversation state machine for interruption handling
- Word-level TTS streaming for low latency
- Prometheus metrics for observability

Protocol:
- Client sends typed events (see api/events.py for ClientEvent types)
- Server sends typed events (see api/events.py for ServerEvent types)
- Binary frames contain audio data (WAV format)

Based on unmute architecture patterns.
"""

import asyncio
import base64
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.events import (
    Error,
    ErrorDetails,
    InputTextCommit,
    KrellInterrupted,
    KrellMetrics,
    KrellStateUpdate,
    ResponseAudioDelta,
    ResponseAudioDone,
    ResponseCreated,
    ResponseDone,
    ResponseTextDelta,
    ResponseTextDone,
    SessionCreated,
    ToolCallCreated,
    ToolResult,
    parse_client_event,
)
from config import Config
from core.conversation_state import ConversationStateMachine, State
from core.metrics import (
    ACTIVE_SESSIONS,
    SESSIONS_TOTAL,
    WEBSOCKET_CONNECTIONS_ACTIVE,
    WEBSOCKET_CONNECTIONS_TOTAL,
    WEBSOCKET_MESSAGES_RECEIVED,
    WEBSOCKET_MESSAGES_SENT,
    WEBSOCKET_BYTES_SENT,
)
from core.stream_utils import TTFTTracker, Stopwatch

logger = logging.getLogger(__name__)

router = APIRouter()
config = Config()


class Session:
    """
    Represents an active WebSocket session.

    Tracks:
    - WebSocket connection
    - Conversation state machine
    - Active generation task (for cancellation)
    - TTFT tracking
    - Interruption state
    """

    def __init__(self, session_id: str, websocket: WebSocket):
        self.session_id = session_id
        self.websocket = websocket
        self.conversation_id: Optional[str] = None
        self.state_machine = ConversationStateMachine(
            on_state_change=self._on_state_change,
            strict=False,  # Don't raise on invalid transitions
        )
        self.active_task: Optional[asyncio.Task] = None
        self.interrupted = False
        self.llm_ttft = TTFTTracker(name="llm")
        self.tts_ttft = TTFTTracker(name="tts")
        self.response_stopwatch = Stopwatch(start=False)

    def _on_state_change(self, old_state: State, new_state: State) -> None:
        """Handle state changes - sends state update to client."""
        logger.debug(f"[{self.session_id}] State: {old_state.value} -> {new_state.value}")

    async def send_event(self, event: Any) -> None:
        """Send a typed event to the client."""
        try:
            data = event.model_dump()
            await self.websocket.send_json(data)
            WEBSOCKET_MESSAGES_SENT.labels(type=event.type).inc()
        except Exception as e:
            logger.error(f"[{self.session_id}] Error sending event: {e}")

    async def send_bytes(self, data: bytes) -> None:
        """Send binary audio data to the client."""
        try:
            await self.websocket.send_bytes(data)
            WEBSOCKET_BYTES_SENT.inc(len(data))
        except Exception as e:
            logger.error(f"[{self.session_id}] Error sending bytes: {e}")

    async def send_state_update(self) -> None:
        """Send current state to client."""
        event = KrellStateUpdate(
            state=self.state_machine.state.value,
        )
        await self.send_event(event)

    def check_interrupted(self) -> bool:
        """Check if the session has been interrupted."""
        return self.interrupted

    def cancel_generation(self) -> None:
        """Cancel any active generation task."""
        self.interrupted = True
        if self.active_task and not self.active_task.done():
            self.active_task.cancel()
            logger.info(f"[{self.session_id}] Cancelled active generation")

    def reset_for_new_response(self) -> None:
        """Reset tracking state for a new response."""
        self.interrupted = False
        self.llm_ttft = TTFTTracker(name="llm")
        self.tts_ttft = TTFTTracker(name="tts")
        self.response_stopwatch = Stopwatch()


class ConnectionManager:
    """Manages active WebSocket sessions."""

    def __init__(self):
        self.sessions: Dict[str, Session] = {}

    async def connect(self, websocket: WebSocket) -> Session:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()

        session_id = str(uuid.uuid4())
        session = Session(session_id, websocket)
        self.sessions[session_id] = session

        # Update metrics
        SESSIONS_TOTAL.inc()
        ACTIVE_SESSIONS.inc()
        WEBSOCKET_CONNECTIONS_ACTIVE.inc()
        WEBSOCKET_CONNECTIONS_TOTAL.labels(status="opened").inc()

        logger.info(f"WebSocket connected: {session_id}")
        return session

    def disconnect(self, session: Session) -> None:
        """Unregister a WebSocket session."""
        session.cancel_generation()
        self.sessions.pop(session.session_id, None)

        # Update metrics
        ACTIVE_SESSIONS.dec()
        WEBSOCKET_CONNECTIONS_ACTIVE.dec()
        WEBSOCKET_CONNECTIONS_TOTAL.labels(status="closed_normal").inc()

        logger.info(f"WebSocket disconnected: {session.session_id}")

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self.sessions.get(session_id)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat.

    Uses OpenAI Realtime API-compatible events with Krell extensions.

    Client Events:
        - input.text.commit: Submit text message
        - session.update: Update session configuration
        - input_audio_buffer.append: Send audio data (future)
        - input_audio_buffer.clear: Clear audio buffer (future)

    Server Events:
        - session.created: Connection established
        - response.created: Response generation started
        - response.text.delta: Streaming text chunk
        - response.text.done: Text complete
        - response.audio.delta: Base64 audio chunk (JSON mode)
        - response.audio.done: Audio complete
        - response.done: Response complete
        - tool_call.created: Tool invocation
        - tool_result: Tool result
        - krell.state.update: State machine update
        - krell.metrics: Latency metrics
        - krell.interrupted: Response interrupted
        - error: Error occurred

    Binary Frames:
        Server sends raw WAV audio as binary frames for low-latency playback.
    """
    session = await manager.connect(websocket)

    try:
        # Send session created event
        await session.send_event(
            SessionCreated(
                session_id=session.session_id,
                conversation_id=session.conversation_id,
            )
        )

        # Main message loop
        while True:
            try:
                # Receive message (could be text or binary)
                message = await websocket.receive()

                # Check for disconnect message
                if message["type"] == "websocket.disconnect":
                    logger.info(f"[{session.session_id}] Received disconnect message")
                    break

                if message["type"] == "websocket.receive":
                    if "text" in message:
                        await handle_text_message(session, message["text"])
                    elif "bytes" in message:
                        await handle_binary_message(session, message["bytes"])

            except WebSocketDisconnect:
                raise
            except RuntimeError as e:
                # Handle "Cannot call receive once disconnect" error
                if "disconnect" in str(e).lower():
                    logger.info(f"[{session.session_id}] Connection already closed")
                    break
                raise
            except Exception as e:
                logger.error(f"[{session.session_id}] Message error: {e}", exc_info=True)
                # Only try to send error if we think connection is still open
                try:
                    await session.send_event(
                        Error(error=ErrorDetails(
                            type="message_error",
                            message=str(e),
                        ))
                    )
                except Exception:
                    # Connection likely closed, exit loop
                    break

    except WebSocketDisconnect:
        pass  # Normal disconnect
    except Exception as e:
        logger.error(f"[{session.session_id}] WebSocket error: {e}", exc_info=True)
        WEBSOCKET_CONNECTIONS_TOTAL.labels(status="closed_error").inc()
    finally:
        manager.disconnect(session)


async def handle_text_message(session: Session, text: str) -> None:
    """Handle incoming text (JSON) message."""
    import json

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        await session.send_event(
            Error(error=ErrorDetails(
                type="json_parse_error",
                message=f"Invalid JSON: {e}",
            ))
        )
        return

    msg_type = data.get("type", "")
    WEBSOCKET_MESSAGES_RECEIVED.labels(type=msg_type).inc()

    # Handle legacy message types for backwards compatibility
    if msg_type == "message":
        # Convert to input.text.commit format
        data = {
            "type": "input.text.commit",
            "text": data.get("content", ""),
            "conversation_id": data.get("conversation_id"),
        }
        msg_type = "input.text.commit"

    elif msg_type == "ping":
        await session.websocket.send_json({"type": "pong"})
        return

    elif msg_type == "cancel":
        session.cancel_generation()
        session.state_machine.interrupt("user cancelled")
        await session.send_event(
            KrellInterrupted(reason="cancel_request")
        )
        return

    # Parse as typed event
    try:
        if msg_type == "input.text.commit":
            event = InputTextCommit.model_validate(data)
            await handle_text_input(session, event)
        else:
            logger.warning(f"[{session.session_id}] Unhandled event type: {msg_type}")

    except Exception as e:
        logger.error(f"[{session.session_id}] Event handling error: {e}", exc_info=True)
        await session.send_event(
            Error(error=ErrorDetails(
                type="event_error",
                message=str(e),
            ))
        )


async def handle_binary_message(session: Session, data: bytes) -> None:
    """
    Handle incoming binary (audio) message.

    Reserved for future audio input support (STT).
    """
    WEBSOCKET_MESSAGES_RECEIVED.labels(type="audio").inc()
    logger.debug(f"[{session.session_id}] Received {len(data)} bytes of audio")
    # TODO: Implement STT processing
    pass


async def handle_text_input(session: Session, event: InputTextCommit) -> None:
    """
    Handle text input submission.

    Coordinates:
    1. State machine transitions
    2. LLM streaming with TTFT tracking
    3. Word-level TTS generation
    4. Interruption handling
    """
    from api.routes import get_krell_agent, tts_service
    from services.tts_streaming import stream_tts_realtime

    content = getattr(event, "text", "") or ""
    if not content.strip():
        await session.send_event(
            Error(error=ErrorDetails(
                type="validation_error",
                message="Empty message content",
            ))
        )
        return

    # Reset for new response
    session.reset_for_new_response()
    session.conversation_id = event.conversation_id

    # Transition to processing state
    session.state_machine.start_processing()
    await session.send_state_update()

    async def generate_response():
        """Inner generation function that can be cancelled."""
        response_id = f"resp_{uuid.uuid4().hex[:12]}"
        full_text_parts = []

        try:
            agent = await get_krell_agent()
            if not agent:
                raise RuntimeError("Failed to initialize agent")

            # Send response created event
            await session.send_event(
                ResponseCreated(
                    response_id=response_id,
                    conversation_id=session.conversation_id,
                    status="in_progress",
                )
            )

            # Start TTFT tracking
            session.llm_ttft.start()

            # Stream text from agent with word-level TTS
            async for item in stream_tts_realtime(
                agent_stream=agent.chat_stream(session.conversation_id, content),
                tts_service=tts_service,
                voice=await _get_voice(),
                lang=config.tts_lang,
                speed=config.tts_speed,
                use_word_streaming=True,
            ):
                # Check for interruption
                if session.check_interrupted():
                    logger.info(f"[{session.session_id}] Response interrupted")
                    await session.send_event(KrellInterrupted(reason="cancel_request"))
                    break

                if isinstance(item, bytes):
                    # Binary audio - send as binary frame for low latency
                    await session.send_bytes(item)

                    # Also send base64 version for clients that prefer JSON
                    # (commented out to reduce bandwidth - enable if needed)
                    # await session.send_event(
                    #     ResponseAudioDelta(
                    #         delta=base64.b64encode(item).decode("utf-8"),
                    #         response_id=response_id,
                    #     )
                    # )

                elif isinstance(item, dict):
                    event_type = item.get("type")

                    if event_type == "conversation_id":
                        session.conversation_id = item.get("conversation_id")

                    elif event_type == "text":
                        text_content = item.get("content", "")
                        full_text_parts.append(text_content)

                        # Record LLM TTFT on first text
                        if session.llm_ttft.is_started and not session.llm_ttft.is_recorded:
                            session.llm_ttft.record_first_token()

                        await session.send_event(
                            ResponseTextDelta(
                                delta=text_content,
                                response_id=response_id,
                            )
                        )

                    elif event_type == "tool_call":
                        session.state_machine.start_tool_execution(item.get("name"))
                        await session.send_event(
                            ToolCallCreated(
                                tool_call_id=item.get("id", ""),
                                name=item.get("name", ""),
                                arguments=item.get("input", {}),
                            )
                        )

                    elif event_type == "tool_result":
                        session.state_machine.tool_execution_complete()
                        await session.send_event(
                            ToolResult(
                                tool_call_id=item.get("tool_use_id", ""),
                                result=item.get("content"),
                            )
                        )

                    elif event_type == "done":
                        # Extract timing info if available
                        timing = item.get("timing", {})
                        break

            # Send completion events
            full_text = "".join(full_text_parts)

            await session.send_event(
                ResponseTextDone(
                    text=full_text,
                    response_id=response_id,
                )
            )

            await session.send_event(
                ResponseAudioDone(response_id=response_id)
            )

            # Send metrics
            await session.send_event(
                KrellMetrics(
                    latency_ms=int(session.response_stopwatch.elapsed_ms),
                    audio_duration_ms=None,  # TODO: track audio duration
                )
            )

            await session.send_event(
                ResponseDone(
                    response_id=response_id,
                    conversation_id=session.conversation_id,
                    status="completed" if not session.interrupted else "cancelled",
                )
            )

        except asyncio.CancelledError:
            logger.info(f"[{session.session_id}] Generation cancelled")
            await session.send_event(
                ResponseDone(
                    response_id=response_id,
                    conversation_id=session.conversation_id,
                    status="cancelled",
                )
            )
            raise

        except Exception as e:
            logger.error(f"[{session.session_id}] Generation error: {e}", exc_info=True)
            session.state_machine.error(str(e))
            await session.send_event(
                Error(error=ErrorDetails(
                    type="generation_error",
                    message=str(e),
                ))
            )
            await session.send_event(
                ResponseDone(
                    response_id=response_id,
                    conversation_id=session.conversation_id,
                    status="failed",
                )
            )

        finally:
            # Return to idle state
            session.state_machine.reset()
            await session.send_state_update()

    # Create and track the generation task
    session.active_task = asyncio.create_task(generate_response())

    try:
        await session.active_task
    except asyncio.CancelledError:
        pass  # Already handled in generate_response
    finally:
        session.active_task = None


async def _get_voice() -> str:
    """Get configured TTS voice from database or config."""
    from database.db import Database

    try:
        database = Database(config.database_path)
        voice = await database.get_setting("tts_voice")
        return voice or config.tts_voice
    except Exception:
        return config.tts_voice


# Legacy compatibility - keep old function signature
async def stream_tts_over_websocket(websocket: WebSocket, text: str):
    """
    Legacy TTS streaming function.

    DEPRECATED: Use stream_tts_realtime from services/tts_streaming.py instead.
    This function is kept for backwards compatibility.
    """
    from services.tts import chunk_text_by_sentences
    import io
    import wave
    import numpy as np
    from api.routes import tts_service

    try:
        if not text or not text.strip():
            logger.warning("[TTS] Empty text, skipping TTS")
            return

        if not tts_service._kyutai_model:
            logger.error("[TTS] Kyutai model not initialized")
            return

        # Send audio start event
        await websocket.send_json({"type": "audio_start", "format": "wav"})

        # Split into sentences
        sentences = chunk_text_by_sentences(text, max_length=200)
        logger.info(f"[TTS] Generating for {len(sentences)} sentences")

        configured_voice = await _get_voice()

        for i, sentence in enumerate(sentences):
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

            # Create WAV
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_array.tobytes())

            await websocket.send_bytes(wav_buffer.getvalue())

        await websocket.send_json({"type": "audio_end"})

    except Exception as e:
        logger.error(f"[TTS] Error: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "message": f"TTS error: {str(e)}",
            "code": "TTS_ERROR",
        })
