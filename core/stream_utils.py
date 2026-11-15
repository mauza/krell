"""
Stream Utilities - Low-latency streaming helpers for LLM and TTS.

This module provides utilities for optimizing streaming latency:
- Word-level rechunking (prevents TTS mispronunciation)
- Exponential moving average for VAD
- TTFT (time-to-first-token) tracking

These are critical for real-time voice AI:
- LLMs stream character-by-character, but TTS needs word boundaries
- VAD needs to smooth noisy signals while staying responsive
- TTFT tracking enables latency monitoring and optimization
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Word-Level Rechunking
# =============================================================================


async def rechunk_to_words(
    iterator: AsyncIterator[str],
    yield_partial_on_punctuation: bool = True,
) -> AsyncIterator[str]:
    """
    Rechunk a character stream into whole words.

    LLMs stream text character-by-character or in small chunks. TTS engines
    need complete words to pronounce correctly. This function buffers until
    word boundaries (whitespace) are detected.

    Example:
        Input stream:  "Hel" "lo, " "wor" "ld!"
        Output stream: "Hello," " world!"

    Args:
        iterator: Async iterator yielding text chunks
        yield_partial_on_punctuation: If True, yield on sentence-ending punctuation
            even without whitespace (reduces latency for short responses)

    Yields:
        Complete words with preserved spacing
    """
    buffer = ""
    space_re = re.compile(r"\s+")
    punctuation_re = re.compile(r"[.!?]$")
    prefix = ""

    async for delta in iterator:
        buffer = buffer + delta

        while True:
            match = space_re.search(buffer)

            if match is None:
                # No whitespace yet - check for sentence-ending punctuation
                if yield_partial_on_punctuation and punctuation_re.search(buffer):
                    # Yield what we have on sentence end (reduces latency)
                    if buffer:
                        yield prefix + buffer
                        prefix = ""
                        buffer = ""
                break

            # Extract word up to whitespace
            chunk = buffer[: match.start()]
            buffer = buffer[match.end() :]

            if chunk:
                yield prefix + chunk
                prefix = " "  # Add space prefix for next word

    # Yield any remaining content
    if buffer:
        yield prefix + buffer


async def rechunk_to_sentences(
    iterator: AsyncIterator[str],
    min_length: int = 20,
) -> AsyncIterator[str]:
    """
    Rechunk a text stream into complete sentences.

    Similar to SentenceBuffer but as an async generator. Useful when you
    want sentence-level TTS but don't need the buffer object.

    Args:
        iterator: Async iterator yielding text chunks
        min_length: Minimum characters before yielding (prevents micro-sentences)

    Yields:
        Complete sentences
    """
    buffer = ""
    sentence_end_re = re.compile(r"([.!?]+)\s*")

    async for delta in iterator:
        buffer += delta

        while True:
            match = sentence_end_re.search(buffer)
            if match is None:
                break

            end_pos = match.end()
            sentence = buffer[:end_pos].strip()
            buffer = buffer[end_pos:]

            if len(sentence) >= min_length:
                yield sentence

    # Yield any remaining content
    if buffer.strip():
        yield buffer.strip()


# =============================================================================
# Exponential Moving Average for VAD
# =============================================================================


class ExponentialMovingAverage:
    """
    Asymmetric exponential moving average for Voice Activity Detection.

    This class smooths noisy VAD signals while maintaining responsiveness.
    The asymmetric design allows different speeds for detecting speech start
    (attack) versus speech end (release).

    Typical values for real-time VAD:
    - attack_time = 0.01 (10ms) - Quick to detect speech start
    - release_time = 0.01 (10ms) - Quick to detect speech end

    Usage:
        ema = ExponentialMovingAverage(attack_time=0.01, release_time=0.01)

        # In audio processing loop:
        for frame in audio_frames:
            vad_signal = vad_model(frame)  # 0.0 to 1.0
            smoothed = ema.update(dt=frame_duration, new_value=vad_signal)

            if smoothed < 0.4:
                print("User is speaking")
            elif smoothed > 0.6:
                print("User stopped speaking")
    """

    def __init__(
        self,
        attack_time: float = 0.01,
        release_time: float = 0.01,
        initial_value: float = 1.0,
    ):
        """
        Initialize the EMA.

        Args:
            attack_time: Time constant for rising values (seconds)
            release_time: Time constant for falling values (seconds)
            initial_value: Starting value (1.0 = assume silence initially)
        """
        self.attack_time = attack_time
        self.release_time = release_time
        self.value = initial_value

    def update(self, dt: float, new_value: float) -> float:
        """
        Update the EMA with a new sample.

        Args:
            dt: Time since last update (seconds)
            new_value: New sample value

        Returns:
            Smoothed value after update
        """
        # Use attack time for rising, release time for falling
        if new_value > self.value:
            time_constant = self.attack_time
        else:
            time_constant = self.release_time

        # Calculate alpha (smoothing factor)
        # alpha approaches 1 as dt increases relative to time constant
        alpha = 1 - np.exp(-dt / time_constant * np.log(2))

        # Apply exponential smoothing
        self.value = float((1 - alpha) * self.value + alpha * new_value)
        return self.value

    def reset(self, value: float = 1.0) -> None:
        """Reset the EMA to a specific value."""
        self.value = value


# =============================================================================
# TTFT (Time to First Token) Tracking
# =============================================================================


@dataclass
class TTFTTracker:
    """
    Tracks Time-to-First-Token for latency monitoring.

    TTFT is a critical metric for real-time AI systems. This class provides
    a simple way to track TTFT across different pipeline stages.

    Usage:
        tracker = TTFTTracker()
        tracker.start()

        # ... wait for first token ...

        ttft = tracker.record_first_token()
        print(f"TTFT: {ttft * 1000:.1f}ms")
    """

    name: str = "default"
    start_time: Optional[float] = field(default=None)
    first_token_time: Optional[float] = field(default=None)
    _recorded: bool = field(default=False)

    def start(self) -> None:
        """Start the TTFT timer."""
        self.start_time = time.perf_counter()
        self._recorded = False

    def record_first_token(self) -> Optional[float]:
        """
        Record the first token and return TTFT.

        Only records once - subsequent calls return the same value.

        Returns:
            TTFT in seconds, or None if not started
        """
        if self.start_time is None:
            return None

        if not self._recorded:
            self.first_token_time = time.perf_counter()
            self._recorded = True

        return self.first_token_time - self.start_time

    @property
    def ttft(self) -> Optional[float]:
        """Get TTFT in seconds, or None if not recorded yet."""
        if self.start_time is None or self.first_token_time is None:
            return None
        return self.first_token_time - self.start_time

    @property
    def ttft_ms(self) -> Optional[float]:
        """Get TTFT in milliseconds, or None if not recorded yet."""
        ttft = self.ttft
        return ttft * 1000 if ttft is not None else None

    @property
    def is_started(self) -> bool:
        """Whether the tracker has been started."""
        return self.start_time is not None

    @property
    def is_recorded(self) -> bool:
        """Whether first token has been recorded."""
        return self._recorded


class Stopwatch:
    """
    High-precision stopwatch for timing operations.

    Usage:
        watch = Stopwatch()
        # ... do something ...
        print(f"Elapsed: {watch.elapsed_ms:.1f}ms")
    """

    def __init__(self, start: bool = True):
        """
        Initialize the stopwatch.

        Args:
            start: Whether to start immediately (default True)
        """
        self._start_time: Optional[float] = None
        self._stop_time: Optional[float] = None
        if start:
            self.start()

    def start(self) -> "Stopwatch":
        """Start or restart the stopwatch."""
        self._start_time = time.perf_counter()
        self._stop_time = None
        return self

    def stop(self) -> float:
        """Stop the stopwatch and return elapsed time."""
        self._stop_time = time.perf_counter()
        return self.elapsed

    def reset(self) -> "Stopwatch":
        """Reset and restart the stopwatch."""
        return self.start()

    @property
    def elapsed(self) -> float:
        """Elapsed time in seconds."""
        if self._start_time is None:
            return 0.0
        end = self._stop_time or time.perf_counter()
        return end - self._start_time

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds."""
        return self.elapsed * 1000

    @property
    def is_running(self) -> bool:
        """Whether the stopwatch is running."""
        return self._start_time is not None and self._stop_time is None


# =============================================================================
# Audio Frame Constants (matching unmute)
# =============================================================================

# Standard sample rate for voice AI
SAMPLE_RATE = 24000

# Samples per frame (80ms at 24kHz)
SAMPLES_PER_FRAME = 1920

# Frame duration in seconds
FRAME_TIME_SEC = 0.08

# Audio buffer delay to prevent playback speedup
AUDIO_BUFFER_SEC = FRAME_TIME_SEC * 4  # 320ms

# Minimum time before VAD can interrupt (echo cancellation settling)
UNINTERRUPTIBLE_BY_VAD_TIME_SEC = 3.0
