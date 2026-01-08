"""
Speech-to-Text (STT) Service

Provides real-time transcription using faster-whisper.
Supports both file-based and streaming transcription.

Install: pip install faster-whisper
"""

import logging
import tempfile
import os
import asyncio
import numpy as np
from typing import Optional, AsyncGenerator, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import faster-whisper
try:
    from faster_whisper import WhisperModel  # type: ignore

    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning(
        "faster-whisper not installed. STT not available. "
        "Install with: pip install faster-whisper"
    )


class STTService:
    """
    Speech-to-Text service using Whisper.

    Features:
    - Real-time transcription
    - Streaming support
    - Multiple language support
    - GPU acceleration
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "default",
    ):
        """
        Initialize STT service.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (auto, cpu, cuda)
            compute_type: Compute type (default, int8, float16)
        """
        if not WHISPER_AVAILABLE:
            raise RuntimeError("faster-whisper not installed")

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

        # Lazy loading - model loaded on first use
        self._model: Optional[WhisperModel] = None  # type: ignore

        logger.info(
            f"STT service initialized: model={model_size}, "
            f"device={device}, compute_type={compute_type}"
        )

    def _ensure_model_loaded(self):
        """Load model if not already loaded"""
        if self._model is None:
            logger.info(f"Loading Whisper model '{self.model_size}'...")

            # Auto-detect device
            device = self.device
            if device == "auto":
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"

            # Auto-detect compute type
            compute_type = self.compute_type
            if compute_type == "default":
                compute_type = "float16" if device == "cuda" else "int8"

            self._model = WhisperModel(  # type: ignore
                self.model_size, device=device, compute_type=compute_type
            )

            logger.info(
                f"Whisper model loaded: device={device}, compute_type={compute_type}"
            )

    async def transcribe_file(
        self, audio_path: str, language: Optional[str] = None
    ) -> Tuple[str, dict]:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to audio file
            language: Language code (e.g., "en", "es"), or None for auto-detect

        Returns:
            Tuple of (transcription_text, info_dict)
        """
        self._ensure_model_loaded()

        # Run transcription in thread pool
        segments, info = await asyncio.to_thread(
            self._model.transcribe,  # type: ignore
            audio_path,
            language=language,
            beam_size=5,
        )

        # Combine all segments
        text = " ".join([seg.text for seg in segments])

        return text.strip(), {
            "language": info.language,
            "duration": info.duration,
            "language_probability": info.language_probability,
        }

    async def transcribe_audio(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> Tuple[str, dict]:
        """
        Transcribe audio from numpy array.

        Args:
            audio_data: Audio samples (float32 or int16)
            sample_rate: Sample rate in Hz
            language: Language code, or None for auto-detect

        Returns:
            Tuple of (transcription_text, info_dict)
        """
        # Convert to float32 if needed
        if audio_data.dtype == np.int16:
            audio_data = audio_data.astype(np.float32) / 32768.0

        # Write to temp file (Whisper requires files)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Write WAV file
            await self._write_wav(tmp_path, audio_data, sample_rate)

            # Transcribe
            text, info = await self.transcribe_file(tmp_path, language)

            return text, info

        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except:
                pass

    async def transcribe_stream(
        self,
        audio_stream: AsyncGenerator[np.ndarray, None],
        sample_rate: int = 16000,
        language: Optional[str] = None,
        chunk_duration: float = 3.0,
    ) -> AsyncGenerator[str, None]:
        """
        Transcribe streaming audio.

        Accumulates audio chunks and transcribes when enough audio is buffered.

        Args:
            audio_stream: Async generator yielding audio chunks
            sample_rate: Sample rate in Hz
            language: Language code
            chunk_duration: Seconds of audio to accumulate before transcribing

        Yields:
            Transcription text for each chunk
        """
        buffer = []
        buffer_duration = 0.0
        target_samples = int(chunk_duration * sample_rate)

        async for audio_chunk in audio_stream:
            buffer.append(audio_chunk)
            buffer_duration += len(audio_chunk) / sample_rate

            # Transcribe when we have enough audio
            if sum(len(chunk) for chunk in buffer) >= target_samples:
                # Combine buffered audio
                combined = np.concatenate(buffer)

                # Transcribe
                try:
                    text, _ = await self.transcribe_audio(
                        combined, sample_rate=sample_rate, language=language
                    )

                    if text.strip():
                        yield text

                except Exception as e:
                    logger.error(f"Transcription error: {e}")

                # Clear buffer
                buffer = []
                buffer_duration = 0.0

        # Transcribe any remaining audio
        if buffer:
            combined = np.concatenate(buffer)
            try:
                text, _ = await self.transcribe_audio(
                    combined, sample_rate=sample_rate, language=language
                )
                if text.strip():
                    yield text
            except Exception as e:
                logger.error(f"Final transcription error: {e}")

    async def _write_wav(self, path: str, audio_data: np.ndarray, sample_rate: int):
        """Write audio to WAV file"""
        import wave

        # Convert to int16
        if audio_data.dtype != np.int16:
            audio_data = np.clip(audio_data, -1.0, 1.0)
            audio_data = (audio_data * 32767).astype(np.int16)

        # Write WAV
        await asyncio.to_thread(self._write_wav_sync, path, audio_data, sample_rate)

    def _write_wav_sync(self, path: str, audio_data: np.ndarray, sample_rate: int):
        """Synchronous WAV writing"""
        import wave

        with wave.open(path, "wb") as wav:
            wav.setnchannels(1)  # Mono
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(sample_rate)
            wav.writeframes(audio_data.tobytes())


# ============================================================================
# Voice Activity Detection (VAD)
# ============================================================================


class SimpleVAD:
    """
    Simple Voice Activity Detector using energy threshold.

    Detects when user starts and stops speaking.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        energy_threshold: float = 0.01,
        speech_frames_required: int = 3,
        silence_frames_required: int = 10,
    ):
        """
        Initialize VAD.

        Args:
            sample_rate: Audio sample rate
            frame_duration_ms: Frame duration in milliseconds
            energy_threshold: Energy threshold for speech detection
            speech_frames_required: Consecutive frames to confirm speech start
            silence_frames_required: Consecutive frames to confirm speech end
        """
        self.sample_rate = sample_rate
        self.frame_size = sample_rate * frame_duration_ms // 1000
        self.energy_threshold = energy_threshold
        self.speech_frames_required = speech_frames_required
        self.silence_frames_required = silence_frames_required

        self.is_speech = False
        self.speech_frame_count = 0
        self.silence_frame_count = 0

        logger.info(f"VAD initialized: threshold={energy_threshold}")

    def process_frame(self, audio_frame: np.ndarray) -> dict:
        """
        Process an audio frame.

        Args:
            audio_frame: Audio samples (float32 or int16)

        Returns:
            Dict with:
                - is_speech: Whether speech is detected
                - speech_started: Whether speech just started
                - speech_ended: Whether speech just ended
        """
        # Convert to float32 if needed
        if audio_frame.dtype == np.int16:
            audio_frame = audio_frame.astype(np.float32) / 32768.0

        # Calculate energy
        energy = np.mean(audio_frame**2)

        # Detect speech
        frame_has_speech = energy > self.energy_threshold

        speech_started = False
        speech_ended = False

        if frame_has_speech:
            self.speech_frame_count += 1
            self.silence_frame_count = 0

            # Speech started?
            if (
                not self.is_speech
                and self.speech_frame_count >= self.speech_frames_required
            ):
                self.is_speech = True
                speech_started = True
                logger.debug("Speech started")

        else:
            self.silence_frame_count += 1
            self.speech_frame_count = 0

            # Speech ended?
            if (
                self.is_speech
                and self.silence_frame_count >= self.silence_frames_required
            ):
                self.is_speech = False
                speech_ended = True
                logger.debug("Speech ended")

        return {
            "is_speech": self.is_speech,
            "speech_started": speech_started,
            "speech_ended": speech_ended,
            "energy": energy,
        }

    def reset(self):
        """Reset VAD state"""
        self.is_speech = False
        self.speech_frame_count = 0
        self.silence_frame_count = 0
