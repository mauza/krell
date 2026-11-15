"""
Speech-to-Text (STT) Service - Voice input transcription.

This module provides real-time speech transcription for voice input.
Currently a placeholder for future implementation.

Planned providers:
- Whisper (local via faster-whisper)
- OpenAI Whisper API
- Google Cloud Speech-to-Text
- Azure Speech Services

Usage:
    from services.stt import STTService

    stt = STTService(provider="whisper")
    await stt.initialize()

    # Transcribe audio
    transcript = await stt.transcribe(audio_bytes)

    # Stream transcription
    async for chunk in stt.transcribe_stream(audio_stream):
        print(chunk.text)

Based on unmute architecture patterns.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, List, Optional, Protocol, Union

import numpy as np

# Protocol imports available if needed for type hints
# from core.protocols import ServiceWithStartup

logger = logging.getLogger(__name__)


class STTProvider(str, Enum):
    """Supported STT providers."""

    WHISPER_LOCAL = "whisper_local"  # faster-whisper
    WHISPER_API = "whisper_api"  # OpenAI API
    GOOGLE = "google"
    AZURE = "azure"


@dataclass
class TranscriptionSegment:
    """A segment of transcribed speech."""

    text: str
    start_time: float  # seconds
    end_time: float  # seconds
    confidence: float = 1.0
    language: Optional[str] = None
    words: List["WordTiming"] = field(default_factory=list)


@dataclass
class WordTiming:
    """Word-level timing information."""

    word: str
    start_time: float
    end_time: float
    confidence: float = 1.0


@dataclass
class TranscriptionResult:
    """Complete transcription result."""

    text: str
    segments: List[TranscriptionSegment] = field(default_factory=list)
    language: Optional[str] = None
    duration: Optional[float] = None
    confidence: float = 1.0


class STTProviderProtocol(Protocol):
    """Protocol for STT provider implementations."""

    async def transcribe(
        self,
        audio: Union[bytes, np.ndarray],
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe audio to text."""
        ...

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> AsyncIterator[TranscriptionSegment]:
        """Stream transcription results."""
        ...


class BaseSTTProvider(ABC):
    """Base class for STT provider implementations."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the provider."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass

    @abstractmethod
    async def transcribe(
        self,
        audio: Union[bytes, np.ndarray],
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe audio to text."""
        pass

    @abstractmethod
    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> AsyncIterator[TranscriptionSegment]:
        """Stream transcription results."""
        pass


class WhisperLocalProvider(BaseSTTProvider):
    """
    Local Whisper transcription using faster-whisper.

    Requires: pip install faster-whisper

    Provides:
    - Local inference (no API calls)
    - GPU acceleration (CUDA, CoreML)
    - Word-level timestamps
    - Language detection
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
    ):
        """
        Initialize Whisper local provider.

        Args:
            model_size: Model size (tiny, base, small, medium, large-v3)
            device: Device to use (auto, cuda, cpu)
            compute_type: Compute type (auto, float16, int8)
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    async def initialize(self) -> None:
        """Initialize the Whisper model."""
        try:
            from faster_whisper import WhisperModel

            logger.info(f"Loading Whisper model: {self.model_size}")
            self._model = await asyncio.to_thread(
                WhisperModel,
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info(f"Whisper model loaded: {self.model_size}")

        except ImportError:
            logger.warning(
                "faster-whisper not installed. Install with: pip install faster-whisper"
            )
            raise

    async def close(self) -> None:
        """Clean up resources."""
        self._model = None

    async def transcribe(
        self,
        audio: Union[bytes, np.ndarray],
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe audio to text."""
        if self._model is None:
            raise RuntimeError("Whisper model not initialized")

        # Convert bytes to numpy if needed
        if isinstance(audio, bytes):
            audio = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

        # Ensure float32 normalized
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
            if audio.max() > 1.0:
                audio = audio / 32768.0

        # Run transcription
        segments_gen, info = await asyncio.to_thread(
            self._model.transcribe,
            audio,
            language=language,
            word_timestamps=True,
        )

        # Collect segments
        segments = []
        full_text_parts = []

        for segment in segments_gen:
            words = []
            if segment.words:
                for word in segment.words:
                    words.append(
                        WordTiming(
                            word=word.word,
                            start_time=word.start,
                            end_time=word.end,
                            confidence=word.probability,
                        )
                    )

            segments.append(
                TranscriptionSegment(
                    text=segment.text,
                    start_time=segment.start,
                    end_time=segment.end,
                    confidence=segment.avg_logprob,
                    language=info.language,
                    words=words,
                )
            )
            full_text_parts.append(segment.text)

        return TranscriptionResult(
            text=" ".join(full_text_parts),
            segments=segments,
            language=info.language,
            duration=info.duration,
            confidence=segments[0].confidence if segments else 1.0,
        )

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> AsyncIterator[TranscriptionSegment]:
        """
        Stream transcription results.

        Note: True streaming requires VAD to detect speech boundaries.
        This implementation buffers and processes periodically.
        """
        buffer = []
        buffer_duration = 0.0
        min_buffer_duration = 1.0  # Minimum 1 second before processing

        async for chunk in audio_stream:
            # Convert chunk to float32
            audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
            buffer.append(audio)
            buffer_duration += len(audio) / sample_rate

            if buffer_duration >= min_buffer_duration:
                # Process buffer
                combined = np.concatenate(buffer)
                result = await self.transcribe(combined, sample_rate, language)

                for segment in result.segments:
                    yield segment

                # Clear buffer
                buffer = []
                buffer_duration = 0.0

        # Process remaining buffer
        if buffer:
            combined = np.concatenate(buffer)
            result = await self.transcribe(combined, sample_rate, language)
            for segment in result.segments:
                yield segment


class STTService:
    """
    Speech-to-Text service with provider abstraction.

    Usage:
        stt = STTService(provider="whisper_local")
        await stt.initialize()

        transcript = await stt.transcribe(audio_bytes)
        print(transcript.text)
    """

    def __init__(
        self,
        provider: str = "whisper_local",
        model_size: str = "base",
        device: str = "auto",
    ):
        """
        Initialize STT service.

        Args:
            provider: STT provider to use
            model_size: Model size (for local providers)
            device: Device to use (for local providers)
        """
        self.provider_name = provider
        self.model_size = model_size
        self.device = device
        self._provider: Optional[BaseSTTProvider] = None

    @property
    def provider(self) -> str:
        """Get provider name."""
        return self.provider_name

    async def initialize(self) -> None:
        """Initialize the STT provider."""
        if self.provider_name == "whisper_local":
            self._provider = WhisperLocalProvider(
                model_size=self.model_size,
                device=self.device,
            )
        else:
            raise ValueError(f"Unsupported STT provider: {self.provider_name}")

        await self._provider.initialize()
        logger.info(f"STT service initialized with provider: {self.provider_name}")

    async def close(self) -> None:
        """Clean up resources."""
        if self._provider:
            await self._provider.close()
            self._provider = None

    async def transcribe(
        self,
        audio: Union[bytes, np.ndarray],
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        Transcribe audio to text.

        Args:
            audio: Audio data (bytes or numpy array)
            sample_rate: Sample rate in Hz
            language: Language code (auto-detect if None)

        Returns:
            TranscriptionResult with text and segments
        """
        if self._provider is None:
            raise RuntimeError("STT service not initialized")

        return await self._provider.transcribe(audio, sample_rate, language)

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> AsyncIterator[TranscriptionSegment]:
        """
        Stream transcription results.

        Args:
            audio_stream: Async iterator of audio chunks
            sample_rate: Sample rate in Hz
            language: Language code (auto-detect if None)

        Yields:
            TranscriptionSegment for each recognized segment
        """
        if self._provider is None:
            raise RuntimeError("STT service not initialized")

        async for segment in self._provider.transcribe_stream(
            audio_stream, sample_rate, language
        ):
            yield segment

    @property
    def is_initialized(self) -> bool:
        """Check if service is initialized."""
        return self._provider is not None


# Convenience function for quick transcription
async def transcribe_audio(
    audio: Union[bytes, np.ndarray],
    sample_rate: int = 16000,
    language: Optional[str] = None,
    provider: str = "whisper_local",
    model_size: str = "base",
) -> TranscriptionResult:
    """
    Quick transcription without managing service lifecycle.

    Note: Creates a new service instance each time.
    For repeated use, create a persistent STTService instance.

    Args:
        audio: Audio data
        sample_rate: Sample rate
        language: Language code
        provider: STT provider
        model_size: Model size

    Returns:
        TranscriptionResult
    """
    stt = STTService(provider=provider, model_size=model_size)
    try:
        await stt.initialize()
        return await stt.transcribe(audio, sample_rate, language)
    finally:
        await stt.close()
