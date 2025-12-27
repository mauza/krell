"""
TTS Streaming Pipeline - Coordinates LLM streaming with real-time TTS generation.

This module provides the core pipeline that enables low-latency voice responses
by generating TTS audio as the LLM produces text, rather than waiting for the
complete response.

Pipeline stages:
1. LLM Stream → Text chunks from agent
2. Sentence Buffer → Complete sentences
3. TTS Generation → Audio for each sentence (IMMEDIATE)
4. Client Stream → Audio bytes sent AS SOON as each sentence is ready

CRITICAL FOR LOW LATENCY:
- Audio is yielded IMMEDIATELY after each sentence is synthesized
- No waiting for the complete response
- Frontend receives first audio within ~1-2 sentences of LLM starting
"""

from typing import AsyncGenerator, Dict, Any, Optional, Union
import asyncio
import logging
import io
import wave
import numpy as np

from services.sentence_buffer import SentenceBuffer
from services.tts import TTSService

logger = logging.getLogger(__name__)


def _create_wav_chunk(audio_data: np.ndarray, sample_rate: int) -> bytes:
    """
    Create a complete WAV file from audio data.

    Each sentence gets its own complete WAV file so it can be played
    independently on the frontend without waiting for other sentences.

    Args:
        audio_data: Audio samples as numpy array (int16)
        sample_rate: Sample rate in Hz

    Returns:
        Complete WAV file as bytes
    """
    # Ensure audio is int16
    if audio_data.dtype != np.int16:
        if audio_data.dtype in [np.float32, np.float64]:
            audio_data = np.clip(audio_data, -1.0, 1.0)
            audio_data = (audio_data * 32767).astype(np.int16)
        else:
            audio_data = audio_data.astype(np.int16)

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_data.tobytes())

    return wav_buffer.getvalue()


async def stream_tts_realtime(
    agent_stream: AsyncGenerator[Dict[str, Any], None],
    tts_service: TTSService,
    voice: str,
    lang: str = "en-us",
    speed: float = 1.0,
    min_sentence_length: int = 20,
    tool_pause_duration: float = 0.5,
) -> AsyncGenerator[Union[bytes, Dict[str, Any]], None]:
    """
    Coordinate LLM streaming with real-time TTS generation.

    CRITICAL: This function yields audio IMMEDIATELY as each sentence completes.
    It does NOT wait for the entire LLM response before starting TTS.

    This function creates a pipeline that:
    - Receives text chunks from the LLM as they're generated
    - Buffers chunks into complete sentences
    - Generates TTS audio for each sentence IMMEDIATELY
    - Yields audio bytes AS SOON as each sentence is ready
    - Handles tool calls with natural pauses

    Args:
        agent_stream: Async generator yielding agent events
        tts_service: TTS service instance for audio generation
        voice: Voice name for TTS
        lang: Language code
        speed: Speech speed multiplier
        min_sentence_length: Minimum characters before generating TTS
        tool_pause_duration: Seconds of silence during tool execution

    Yields:
        Either:
        - bytes: WAV audio data for a sentence (ready to play immediately)
        - Dict: Event passthrough (conversation_id, text, tool_call, etc.)
    """
    sentence_buffer = SentenceBuffer(min_sentence_length=min_sentence_length)
    sample_rate = 24000  # Default, will be updated from first TTS call

    # Track full text for logging
    full_text_parts = []
    sentences_generated = 0

    logger.info("Starting real-time TTS streaming pipeline (immediate audio)")
    event_count = 0

    try:
        logger.info("[TTS PIPELINE] Waiting for first event from agent_stream...")
        async for event in agent_stream:
            event_count += 1
            logger.info(
                f"[TTS PIPELINE] Received event #{event_count}: type={event.get('type', 'unknown')}"
            )
            event_type = event.get("type")

            # Text chunk from LLM - process immediately
            if event_type == "text":
                text_chunk = event.get("content", "")
                full_text_parts.append(text_chunk)

                # Pass through text event so frontend can display it
                yield event

                # Add to sentence buffer and get complete sentences
                sentences = sentence_buffer.add_chunk(text_chunk)

                # Generate and yield audio for each complete sentence IMMEDIATELY
                for sentence in sentences:
                    logger.info(f"[IMMEDIATE TTS] Generating for: {sentence[:50]}...")
                    sentences_generated += 1

                    # Generate audio for this sentence
                    audio_data, rate = await _generate_tts_for_sentence(
                        tts_service=tts_service,
                        text=sentence,
                        voice=voice,
                        lang=lang,
                        speed=speed,
                    )
                    sample_rate = rate

                    # Create WAV and yield IMMEDIATELY - don't wait for more sentences
                    wav_bytes = _create_wav_chunk(audio_data, sample_rate)
                    logger.info(
                        f"[IMMEDIATE TTS] Yielding {len(wav_bytes)} bytes for sentence {sentences_generated}"
                    )
                    yield wav_bytes

            # Tool call - pass through and insert pause
            elif event_type == "tool_call":
                yield event
                tool_name = event.get("name", "unknown")
                logger.info(f"Tool call detected: {tool_name}, inserting pause")

                # Generate silence for pause
                pause_samples = int(sample_rate * tool_pause_duration)
                silence = np.zeros(pause_samples, dtype=np.int16)
                wav_bytes = _create_wav_chunk(silence, sample_rate)
                yield wav_bytes

            # Tool result - pass through
            elif event_type == "tool_result":
                yield event
                logger.debug("Tool result received (LLM will generate response text)")

            # Conversation ID - pass through
            elif event_type == "conversation_id":
                yield event
                logger.debug(f"Conversation ID: {event.get('conversation_id')}")

            # Stream complete - process any remaining buffered text
            elif event_type == "done":
                logger.info("Agent stream complete, flushing remaining buffer")

                # Flush any remaining text in buffer
                remaining = sentence_buffer.flush()
                if remaining:
                    logger.info(
                        f"[IMMEDIATE TTS] Generating for final text: {remaining[:50]}..."
                    )
                    sentences_generated += 1

                    audio_data, rate = await _generate_tts_for_sentence(
                        tts_service=tts_service,
                        text=remaining,
                        voice=voice,
                        lang=lang,
                        speed=speed,
                    )

                    # Yield final audio chunk immediately
                    wav_bytes = _create_wav_chunk(audio_data, rate)
                    logger.info(
                        f"[IMMEDIATE TTS] Yielding {len(wav_bytes)} bytes for final sentence"
                    )
                    yield wav_bytes

                # Pass through done event
                yield event

    except Exception as e:
        logger.error(f"Error in TTS streaming pipeline: {e}", exc_info=True)
        raise

    full_text = "".join(full_text_parts)
    logger.info(
        f"Streaming complete. Generated {sentences_generated} audio chunks "
        f"for {len(full_text)} characters of text"
    )


async def _generate_tts_for_sentence(
    tts_service: TTSService,
    text: str,
    voice: str,
    lang: str,
    speed: float,
) -> tuple[np.ndarray, int]:
    """
    Generate TTS audio for a single sentence.

    Args:
        tts_service: TTS service instance
        text: Sentence text
        voice: Voice name
        lang: Language code
        speed: Speech speed

    Returns:
        Tuple of (audio_array, sample_rate)
    """
    # Use the appropriate TTS model based on provider
    if tts_service.provider == "kyutai":
        if not tts_service._kyutai_model:
            raise RuntimeError("Kyutai TTS model not initialized")

        # Generate synchronously in thread pool to avoid blocking
        audio_array, sample_rate = await asyncio.to_thread(
            tts_service._kyutai_model.synthesize,
            text=text,
            voice=voice,
            speed=speed,
            lang=lang,
        )

    else:
        raise ValueError(f"Unsupported TTS provider: {tts_service.provider}")

    # Ensure audio is int16
    if audio_array.dtype != np.int16:
        if audio_array.dtype in [np.float32, np.float64]:
            audio_array = np.clip(audio_array, -1.0, 1.0)
            audio_array = (audio_array * 32767).astype(np.int16)
        else:
            audio_array = audio_array.astype(np.int16)

    return audio_array, sample_rate
