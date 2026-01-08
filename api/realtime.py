"""
Krell Realtime API - OpenAI Realtime API Compatible Endpoint

WebSocket endpoint for continuous voice conversations.
Uses the dual-loop pattern from Unmute:
- receive_loop: Handles incoming audio and events from browser
- emit_loop: Sends outgoing audio and events to browser

Usage:
    const ws = new WebSocket('ws://localhost:8000/v1/realtime');

    // Send audio
    ws.send(JSON.stringify({
        type: 'input_audio_buffer.append',
        audio: base64_opus
    }));

    // Receive events
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'response.audio.delta') {
            // Play audio
        }
    };
"""

import asyncio
import base64
import json
import logging
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.websockets import WebSocketState
from pydantic import ValidationError
from typing import Optional

from core.realtime_handler import KrellRealtimeHandler, ConversationState
from services.stt import STTService
from services.opus_audio import create_audio_processor, SAMPLE_RATE
import api.realtime_events as events

logger = logging.getLogger(__name__)

router = APIRouter()

# Connection limiting (like Unmute)
MAX_CONCURRENT_SESSIONS = 4  # Adjust based on GPU memory
SESSION_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_SESSIONS)


@router.websocket("/v1/realtime")
async def realtime_endpoint(websocket: WebSocket):
    """
    OpenAI Realtime API compatible WebSocket endpoint.

    Implements continuous voice conversation with:
    - Streaming STT (speech-to-text)
    - Streaming LLM generation
    - Streaming TTS (text-to-speech)
    - Opus audio codec
    - Voice Activity Detection
    - Interruption support
    """
    session_id = str(uuid.uuid4())

    async with SESSION_SEMAPHORE:
        logger.info(
            f"[{session_id}] New realtime connection "
            f"({SESSION_SEMAPHORE._value} slots remaining)"
        )

        try:
            # Accept WebSocket with OpenAI protocol
            await websocket.accept(subprotocol="realtime")

            # Initialize handler
            handler = await _create_handler(session_id)

            async with handler:
                await handler.startup()

                # Run dual loops concurrently
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(
                        receive_loop(websocket, handler, session_id),
                        name=f"receive_loop_{session_id}",
                    )
                    tg.create_task(
                        emit_loop(websocket, handler, session_id),
                        name=f"emit_loop_{session_id}",
                    )

        except* WebSocketDisconnect as eg:
            logger.info(f"[{session_id}] WebSocket disconnected")

        except* Exception as eg:
            # Handle exception group from TaskGroup
            for exc in eg.exceptions:
                if isinstance(exc, WebSocketDisconnect):
                    logger.info(f"[{session_id}] WebSocket disconnected")
                else:
                    logger.error(
                        f"[{session_id}] Error in realtime endpoint: {exc}",
                        exc_info=exc,
                    )

                    try:
                        if websocket.application_state == WebSocketState.CONNECTED:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "error": {
                                        "type": "server_error",
                                        "message": str(exc),
                                    },
                                }
                            )
                    except:
                        pass

        finally:
            logger.info(f"[{session_id}] Session ended")


async def _create_handler(session_id: str) -> KrellRealtimeHandler:
    """
    Create and initialize the realtime handler.

    This loads all required services (STT, TTS, LLM).
    """
    from api.routes import get_krell_agent, tts_service

    # Get agent
    agent = await get_krell_agent()
    if not agent:
        raise RuntimeError("Failed to initialize agent")

    # Initialize STT service
    stt_service = STTService(
        model_size="base",  # fast enough for real-time
        device="auto",
        compute_type="default",
    )

    # Create handler
    handler = KrellRealtimeHandler(
        agent=agent,
        tts_service=tts_service,
        stt_service=stt_service,
        session_config=events.SessionConfig(
            input_audio_format="opus",
            output_audio_format="opus",
            voice=tts_service.voice,
        ),
    )

    logger.info(f"[{session_id}] Handler created")
    return handler


async def receive_loop(
    websocket: WebSocket, handler: KrellRealtimeHandler, session_id: str
):
    """
    Receive loop - processes incoming messages from browser.

    Handles:
    - Audio chunks (Opus, base64-encoded)
    - Session updates
    - Response cancellation
    """
    audio_processor = create_audio_processor(sample_rate=SAMPLE_RATE)

    logger.info(f"[{session_id}] Receive loop started")

    try:
        while True:
            # Receive message from browser
            try:
                message_raw = await websocket.receive_text()
            except RuntimeError as e:
                if "WebSocket is not connected" in str(e):
                    logger.info(f"[{session_id}] WebSocket closed")
                    raise WebSocketDisconnect()
                raise

            # Parse event
            try:
                message_dict = json.loads(message_raw)
                event_type = message_dict.get("type")

                # Route based on event type
                if event_type == "input_audio_buffer.append":
                    await _handle_audio_append(
                        handler, audio_processor, message_dict, session_id
                    )

                elif event_type == "session.update":
                    await _handle_session_update(handler, message_dict, session_id)

                elif event_type == "response.cancel":
                    await _handle_response_cancel(handler, session_id)

                else:
                    logger.warning(f"[{session_id}] Unknown event type: {event_type}")

            except json.JSONDecodeError as e:
                logger.error(f"[{session_id}] Invalid JSON: {e}")
                await websocket.send_json(
                    events.make_error(
                        events.ErrorType.INVALID_REQUEST, f"Invalid JSON: {e}"
                    ).model_dump()
                )

            except Exception as e:
                logger.error(
                    f"[{session_id}] Error processing message: {e}", exc_info=True
                )

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] Receive loop stopped (disconnect)")
        raise

    except Exception as e:
        logger.error(f"[{session_id}] Receive loop error: {e}", exc_info=True)
        raise


async def _handle_audio_append(
    handler: KrellRealtimeHandler, audio_processor, message: dict, session_id: str
):
    """Handle incoming audio chunk"""
    audio_base64 = message.get("audio", "")

    # Decode Opus audio
    try:
        pcm_audio = await audio_processor.decode_base64_opus_to_pcm(audio_base64)

        # Send to handler
        await handler.receive((SAMPLE_RATE, pcm_audio))

    except Exception as e:
        logger.error(f"[{session_id}] Error decoding audio: {e}")


async def _handle_session_update(
    handler: KrellRealtimeHandler, message: dict, session_id: str
):
    """Handle session configuration update"""
    try:
        event = events.SessionUpdate(**message)
        await handler.update_session(event.session)

        # Send confirmation
        await handler.event_queue.put(events.SessionUpdated(session=event.session))

        logger.info(f"[{session_id}] Session updated")

    except ValidationError as e:
        logger.error(f"[{session_id}] Invalid session update: {e}")


async def _handle_response_cancel(handler: KrellRealtimeHandler, session_id: str):
    """Handle response cancellation (user interruption)"""
    logger.info(f"[{session_id}] Response cancelled by client")
    await handler.cancel_response()


async def emit_loop(
    websocket: WebSocket, handler: KrellRealtimeHandler, session_id: str
):
    """
    Emit loop - sends outgoing events to browser.

    Continuously polls handler.emit() for events and sends them.
    Uses non-blocking pattern like Unmute.
    """
    logger.info(f"[{session_id}] Emit loop started")

    try:
        while True:
            # Check WebSocket state
            if (
                websocket.application_state == WebSocketState.DISCONNECTED
                or websocket.client_state == WebSocketState.DISCONNECTED
            ):
                logger.info(f"[{session_id}] WebSocket disconnected in emit loop")
                raise WebSocketDisconnect()

            # Get next event (non-blocking)
            event = await handler.emit()

            if event is None:
                # No event ready - small sleep to avoid busy loop
                await asyncio.sleep(0.01)  # 10ms
                continue

            # Send event to browser
            try:
                event_json = event.model_dump_json()
                await websocket.send_text(event_json)

                # Debug logging (throttled)
                if event.type.startswith("response.audio.delta"):
                    # Too verbose, skip
                    pass
                else:
                    logger.debug(f"[{session_id}] Sent: {event.type}")

            except WebSocketDisconnect:
                logger.info(f"[{session_id}] WebSocket disconnected while sending")
                raise

            except RuntimeError as e:
                if "Unexpected ASGI message" in str(e) or "WebSocket" in str(e):
                    logger.info(f"[{session_id}] WebSocket closed while sending")
                    raise WebSocketDisconnect()
                raise

    except WebSocketDisconnect:
        logger.info(f"[{session_id}] Emit loop stopped (disconnect)")
        raise

    except Exception as e:
        logger.error(f"[{session_id}] Emit loop error: {e}", exc_info=True)
        raise


# ============================================================================
# Health Check
# ============================================================================


@router.get("/v1/realtime/health")
async def realtime_health():
    """
    Health check for realtime endpoint.

    Returns status of required services.
    """
    from api.routes import tts_service

    # Check TTS
    tts_ready = (
        hasattr(tts_service, "_kyutai_model") and tts_service._kyutai_model is not None
    )

    # Check STT (lazy loaded)
    stt_ready = True  # Will be loaded on first connection

    # Check available slots
    available_slots = SESSION_SEMAPHORE._value

    status_ok = tts_ready and stt_ready and available_slots > 0

    return {
        "status": "healthy" if status_ok else "degraded",
        "tts_ready": tts_ready,
        "stt_ready": stt_ready,
        "available_slots": available_slots,
        "max_concurrent_sessions": MAX_CONCURRENT_SESSIONS,
    }
