"""
Krell Realtime Handler

Orchestrates the continuous conversation pipeline:
1. Receives audio from browser (Opus)
2. Processes with STT (faster-whisper)
3. Detects end-of-speech with VAD
4. Generates LLM response (streaming)
5. Generates TTS audio (streaming)
6. Sends back to browser (Opus)

This is inspired by Unmute's UnmuteHandler but adapted for Krell's architecture.
"""

import logging
import asyncio
import numpy as np
import uuid
from typing import Optional, AsyncGenerator
from enum import Enum

from api.realtime_events import (
    ServerEvent,
    SessionConfig,
    SessionCreated,
    InputAudioBufferCommitted,
    InputAudioBufferCleared,
    ResponseCreated,
    ResponseDone,
    ResponseTextDelta,
    ResponseAudioDelta,
    InputAudioTranscriptionDelta,
    InputAudioTranscriptionCompleted,
    KrellDebugInfo,
    make_text_delta,
    make_audio_delta,
    make_transcription_delta,
    make_transcription_completed,
)
from services.stt import STTService, SimpleVAD
from services.opus_audio import create_audio_processor, SAMPLE_RATE
from services.tts import TTSService
from core.agent import KrellAgent

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """States of the conversation flow"""

    IDLE = "idle"  # Waiting for user to speak
    LISTENING = "listening"  # User is speaking
    PROCESSING = "processing"  # Transcribing and generating response
    SPEAKING = "speaking"  # AI is speaking
    INTERRUPTED = "interrupted"  # User interrupted AI


class KrellRealtimeHandler:
    """
    Handles real-time voice conversation flow.

    Inspired by Unmute's architecture with dual loops:
    - receive(): Process incoming audio from browser
    - emit(): Yield outgoing events/audio to browser
    """

    def __init__(
        self,
        agent: KrellAgent,
        tts_service: TTSService,
        stt_service: STTService,
        session_config: Optional[SessionConfig] = None,
    ):
        """
        Initialize realtime handler.

        Args:
            agent: Krell agent for LLM interactions
            tts_service: TTS service for speech synthesis
            stt_service: STT service for transcription
            session_config: Initial session configuration
        """
        self.agent = agent
        self.tts_service = tts_service
        self.stt_service = stt_service

        # Session configuration
        self.session_config = session_config or SessionConfig()

        # Audio processors
        self.audio_processor = create_audio_processor(sample_rate=SAMPLE_RATE)

        # Voice Activity Detection
        self.vad = SimpleVAD(
            sample_rate=SAMPLE_RATE,
            energy_threshold=0.01,
            silence_frames_required=15,  # ~450ms of silence to end speech
        )

        # State
        self.state = ConversationState.IDLE
        self.conversation_id: Optional[str] = None

        # Audio buffers
        self.audio_buffer: list[np.ndarray] = []  # Incoming user audio
        self.buffered_audio_duration = 0.0

        # Event queue for emit()
        self.event_queue: asyncio.Queue[ServerEvent] = asyncio.Queue()

        # Current item ID (for tracking messages)
        self.current_item_id = str(uuid.uuid4())

        # Flags
        self.is_generating = False
        self.should_stop = False

        logger.info("Krell Realtime Handler initialized")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()

    async def startup(self):
        """Send initial session created event"""
        await self.event_queue.put(SessionCreated(session=self.session_config))

    async def cleanup(self):
        """Clean up resources"""
        self.should_stop = True
        logger.info("Realtime handler cleaned up")

    async def receive(self, audio_chunk: tuple[int, np.ndarray]):
        """
        Process incoming audio from browser.

        This is called by the receive_loop when new audio arrives.

        Args:
            audio_chunk: Tuple of (sample_rate, audio_data)
        """
        sample_rate, audio_data = audio_chunk

        # Add to buffer
        self.audio_buffer.append(audio_data)
        self.buffered_audio_duration += len(audio_data) / sample_rate

        # Process with VAD
        vad_result = self.vad.process_frame(audio_data)

        # Speech started?
        if vad_result["speech_started"]:
            await self._on_speech_started()

        # Speech ended?
        elif vad_result["speech_ended"]:
            await self._on_speech_ended()

        # Debug event
        if vad_result["is_speech"]:
            await self.event_queue.put(
                KrellDebugInfo(
                    state=self.state.value,
                    buffers={
                        "audio_buffer_duration": self.buffered_audio_duration,
                        "audio_buffer_chunks": len(self.audio_buffer),
                    },
                )
            )

    async def _on_speech_started(self):
        """User started speaking"""
        logger.info("User started speaking")

        # If AI is currently speaking, interrupt it
        if self.state == ConversationState.SPEAKING:
            logger.info("User interrupted AI")
            self.state = ConversationState.INTERRUPTED
            self.is_generating = False
            # Event queue will be cleared by the generation task

        # Update state
        self.state = ConversationState.LISTENING
        self.current_item_id = str(uuid.uuid4())

        # Clear old audio buffer
        self.audio_buffer = []
        self.buffered_audio_duration = 0.0

    async def _on_speech_ended(self):
        """User stopped speaking - start processing"""
        logger.info(
            f"User stopped speaking ({self.buffered_audio_duration:.2f}s of audio)"
        )

        # Commit audio buffer
        await self.event_queue.put(InputAudioBufferCommitted())

        # Combine buffered audio
        if not self.audio_buffer:
            logger.warning("No audio to transcribe")
            self.state = ConversationState.IDLE
            return

        combined_audio = np.concatenate(self.audio_buffer)

        # Update state
        self.state = ConversationState.PROCESSING

        # Start processing (transcribe + generate response)
        asyncio.create_task(self._process_user_audio(combined_audio))

        # Clear buffer
        self.audio_buffer = []
        self.buffered_audio_duration = 0.0
        await self.event_queue.put(InputAudioBufferCleared())

    async def _process_user_audio(self, audio: np.ndarray):
        """
        Process user's audio: transcribe → LLM → TTS

        Args:
            audio: User's audio (PCM, 24kHz)
        """
        try:
            # 1. Transcribe audio
            logger.info("Transcribing user audio...")
            text, info = await self.stt_service.transcribe_audio(
                audio, sample_rate=SAMPLE_RATE, language="en"
            )

            logger.info(f"Transcription: '{text}'")

            # Send transcription complete event
            await self.event_queue.put(
                make_transcription_completed(text, self.current_item_id)
            )

            if not text.strip():
                logger.warning("Empty transcription, ignoring")
                self.state = ConversationState.IDLE
                return

            # 2. Generate LLM response (streaming)
            logger.info("Generating LLM response...")
            self.is_generating = True
            self.state = ConversationState.PROCESSING

            response_id = str(uuid.uuid4())
            await self.event_queue.put(ResponseCreated(response={"id": response_id}))

            # Stream LLM response and generate TTS simultaneously
            full_text = []

            async for event in self.agent.chat_stream(self.conversation_id, text):
                # Check if interrupted
                if not self.is_generating:
                    logger.info("Generation interrupted")
                    return

                event_type = event.get("type")

                if event_type == "conversation_id":
                    self.conversation_id = event["conversation_id"]

                elif event_type == "text":
                    text_chunk = event["content"]
                    full_text.append(text_chunk)

                    # Send text delta
                    await self.event_queue.put(make_text_delta(text_chunk, response_id))

                elif event_type == "done":
                    # LLM generation complete - now generate TTS
                    response_text = "".join(full_text)
                    logger.info(f"LLM complete: '{response_text[:50]}...'")

                    # Start TTS generation
                    await self._generate_tts(response_text, response_id)

            # Mark response as done
            await self.event_queue.put(ResponseDone(response={"id": response_id}))

            self.is_generating = False
            self.state = ConversationState.IDLE

        except Exception as e:
            logger.error(f"Error processing user audio: {e}", exc_info=True)
            self.state = ConversationState.IDLE
            self.is_generating = False

    async def _generate_tts(self, text: str, response_id: str):
        """
        Generate TTS audio and queue it for sending.

        Args:
            text: Text to synthesize
            response_id: Response ID for tracking
        """
        if not text.strip():
            return

        logger.info(f"Generating TTS for: '{text[:50]}...'")
        self.state = ConversationState.SPEAKING

        # Get configured voice
        voice = self.session_config.voice or self.tts_service.voice

        # Generate TTS using Kyutai model (sentence by sentence for low latency)
        from services.sentence_buffer import SentenceBuffer

        sentence_buffer = SentenceBuffer(min_sentence_length=20)
        sentences = sentence_buffer.add_chunk(text)
        remaining = sentence_buffer.flush()
        if remaining:
            sentences.append(remaining)

        for sentence in sentences:
            # Check if interrupted
            if not self.is_generating:
                logger.info("TTS interrupted")
                return

            logger.info(f"Synthesizing sentence: '{sentence[:40]}...'")

            # Generate audio for sentence
            audio_array, sample_rate = await asyncio.to_thread(
                self.tts_service._kyutai_model.synthesize,
                text=sentence,
                voice=voice,
                speed=1.0,
                lang="en-us",
            )

            # Convert to int16
            if audio_array.dtype != np.int16:
                if audio_array.dtype in [np.float32, np.float64]:
                    audio_array = np.clip(audio_array, -1.0, 1.0)
                    audio_array = (audio_array * 32767).astype(np.int16)
                else:
                    audio_array = audio_array.astype(np.int16)

            # Encode to Opus and base64
            base64_frames = await self.audio_processor.encode_pcm_to_base64_opus(
                audio_array
            )

            # Queue audio deltas
            for base64_audio in base64_frames:
                await self.event_queue.put(make_audio_delta(base64_audio, response_id))

        logger.info("TTS complete")

    async def emit(self) -> Optional[ServerEvent]:
        """
        Get next event to send to browser.

        This is called by the emit_loop to get events to send.

        Returns:
            Next server event, or None if queue is empty
        """
        try:
            return self.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def update_session(self, session: SessionConfig):
        """Update session configuration"""
        self.session_config = session
        logger.info(f"Session updated: voice={session.voice}")

    async def cancel_response(self):
        """Cancel ongoing response generation (user interruption)"""
        logger.info("Cancelling response")
        self.is_generating = False

        # Clear event queue of pending audio
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Reset state
        self.state = ConversationState.IDLE
