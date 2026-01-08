"""
Opus Audio Codec Support

Handles encoding/decoding of Opus audio for real-time streaming.
Opus is ideal for voice because:
- Low latency (~20-60ms frames)
- Excellent compression (32-48kbps for voice)
- Handles packet loss gracefully
- Native browser support

Install: pip install opuslib
"""

import base64
import logging
import numpy as np
from typing import Optional, Tuple
import asyncio

logger = logging.getLogger(__name__)

# Try to import opuslib, but make it optional for systems without it
try:
    import opuslib  # type: ignore

    OPUS_AVAILABLE = True
    # Define constants to avoid type errors
    APPLICATION_VOIP = opuslib.APPLICATION_VOIP  # type: ignore
    APPLICATION_AUDIO = opuslib.APPLICATION_AUDIO  # type: ignore
    APPLICATION_RESTRICTED_LOWDELAY = opuslib.APPLICATION_RESTRICTED_LOWDELAY  # type: ignore
except ImportError:
    OPUS_AVAILABLE = False
    # Define dummy constants
    APPLICATION_VOIP = 2048
    APPLICATION_AUDIO = 2049
    APPLICATION_RESTRICTED_LOWDELAY = 2051
    logger.warning(
        "opuslib not installed. Opus codec not available. "
        "Install with: pip install opuslib"
    )


# Audio constants
SAMPLE_RATE = 24000  # 24kHz - good balance of quality and bandwidth
CHANNELS = 1  # Mono
FRAME_DURATION_MS = 20  # 20ms frames (common for voice)
FRAME_SIZE = SAMPLE_RATE * FRAME_DURATION_MS // 1000  # 480 samples at 24kHz


class OpusEncoder:
    """
    Encode PCM audio to Opus format for efficient streaming.

    Example:
        encoder = OpusEncoder()
        opus_bytes = encoder.encode(pcm_audio)
        base64_opus = base64.b64encode(opus_bytes).decode('utf-8')
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        application: str = "voip",
    ):
        if not OPUS_AVAILABLE:
            raise RuntimeError("opuslib not installed")

        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = sample_rate * FRAME_DURATION_MS // 1000

        # Application types:
        # - voip: Voice over IP (optimized for speech)
        # - audio: General audio
        # - restricted_lowdelay: Low latency mode
        app_type = {
            "voip": APPLICATION_VOIP,
            "audio": APPLICATION_AUDIO,
            "restricted_lowdelay": APPLICATION_RESTRICTED_LOWDELAY,
        }.get(application, APPLICATION_VOIP)

        self.encoder = opuslib.Encoder(  # type: ignore
            fs=sample_rate, channels=channels, application=app_type
        )

        # Buffer for incomplete frames
        self.buffer = np.array([], dtype=np.int16)

        logger.info(
            f"Opus encoder initialized: {sample_rate}Hz, {channels}ch, "
            f"frame_size={self.frame_size} ({FRAME_DURATION_MS}ms)"
        )

    def encode(self, pcm_audio: np.ndarray) -> bytes:
        """
        Encode PCM audio to Opus.

        Args:
            pcm_audio: Audio samples as int16 numpy array

        Returns:
            Opus-encoded audio as bytes
        """
        if pcm_audio.dtype != np.int16:
            pcm_audio = self._convert_to_int16(pcm_audio)

        # Ensure we have exactly one frame
        if len(pcm_audio) != self.frame_size:
            # Pad or truncate to frame size
            if len(pcm_audio) < self.frame_size:
                pcm_audio = np.pad(pcm_audio, (0, self.frame_size - len(pcm_audio)))
            else:
                pcm_audio = pcm_audio[: self.frame_size]

        # Encode
        opus_bytes = self.encoder.encode(pcm_audio.tobytes(), self.frame_size)
        return opus_bytes

    def encode_stream(self, pcm_audio: np.ndarray) -> list[bytes]:
        """
        Encode a stream of PCM audio, handling buffering.

        This method:
        1. Appends new audio to internal buffer
        2. Encodes complete frames
        3. Keeps leftover samples for next call

        Args:
            pcm_audio: Audio samples as int16 numpy array

        Returns:
            List of Opus-encoded frames
        """
        if pcm_audio.dtype != np.int16:
            pcm_audio = self._convert_to_int16(pcm_audio)

        # Add to buffer
        self.buffer = np.concatenate([self.buffer, pcm_audio])

        # Encode all complete frames
        encoded_frames = []
        while len(self.buffer) >= self.frame_size:
            frame = self.buffer[: self.frame_size]
            self.buffer = self.buffer[self.frame_size :]

            opus_bytes = self.encoder.encode(frame.tobytes(), self.frame_size)
            encoded_frames.append(opus_bytes)

        return encoded_frames

    def flush(self) -> Optional[bytes]:
        """
        Flush remaining buffer (pad and encode).

        Call this when stream ends to encode any leftover audio.
        """
        if len(self.buffer) == 0:
            return None

        # Pad to frame size
        padded = np.pad(self.buffer, (0, self.frame_size - len(self.buffer)))
        self.buffer = np.array([], dtype=np.int16)

        return self.encoder.encode(padded.tobytes(), self.frame_size)

    def _convert_to_int16(self, audio: np.ndarray) -> np.ndarray:
        """Convert audio to int16 format"""
        if audio.dtype in [np.float32, np.float64]:
            audio = np.clip(audio, -1.0, 1.0)
            audio = (audio * 32767).astype(np.int16)
        else:
            audio = audio.astype(np.int16)
        return audio


class OpusDecoder:
    """
    Decode Opus audio to PCM format.

    Example:
        decoder = OpusDecoder()
        opus_bytes = base64.b64decode(base64_opus)
        pcm_audio = decoder.decode(opus_bytes)
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        if not OPUS_AVAILABLE:
            raise RuntimeError("opuslib not installed")

        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = sample_rate * FRAME_DURATION_MS // 1000

        self.decoder = opuslib.Decoder(fs=sample_rate, channels=channels)  # type: ignore

        logger.info(
            f"Opus decoder initialized: {sample_rate}Hz, {channels}ch, "
            f"frame_size={self.frame_size}"
        )

    def decode(self, opus_bytes: bytes) -> np.ndarray:
        """
        Decode Opus audio to PCM.

        Args:
            opus_bytes: Opus-encoded audio

        Returns:
            PCM audio as int16 numpy array
        """
        pcm_bytes = self.decoder.decode(opus_bytes, self.frame_size)
        pcm_audio = np.frombuffer(pcm_bytes, dtype=np.int16)
        return pcm_audio


class OpusStreamProcessor:
    """
    Helper class for processing streams of Opus audio.

    Handles base64 encoding/decoding and frame buffering.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.encoder = OpusEncoder(sample_rate=sample_rate) if OPUS_AVAILABLE else None
        self.decoder = OpusDecoder(sample_rate=sample_rate) if OPUS_AVAILABLE else None
        self.sample_rate = sample_rate

    async def encode_pcm_to_base64_opus(self, pcm_audio: np.ndarray) -> list[str]:
        """
        Encode PCM audio and return list of base64-encoded Opus frames.

        Args:
            pcm_audio: Audio samples as numpy array (any dtype)

        Returns:
            List of base64-encoded Opus frames
        """
        if not self.encoder:
            raise RuntimeError("Opus encoder not available")

        # Run encoding in thread pool (can be CPU intensive)
        frames = await asyncio.to_thread(self.encoder.encode_stream, pcm_audio)

        # Convert to base64
        base64_frames = [base64.b64encode(frame).decode("utf-8") for frame in frames]
        return base64_frames

    async def decode_base64_opus_to_pcm(self, base64_opus: str) -> np.ndarray:
        """
        Decode base64-encoded Opus audio to PCM.

        Args:
            base64_opus: Base64-encoded Opus frame

        Returns:
            PCM audio as int16 numpy array
        """
        if not self.decoder:
            raise RuntimeError("Opus decoder not available")

        opus_bytes = base64.b64decode(base64_opus)

        # Run decoding in thread pool
        pcm_audio = await asyncio.to_thread(self.decoder.decode, opus_bytes)
        return pcm_audio


# ============================================================================
# Fallback: PCM16 support (when Opus not available)
# ============================================================================


class PCM16Processor:
    """
    Fallback processor using raw PCM16 audio (no Opus).

    Less efficient (5-8x larger) but works without opuslib.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        logger.warning(
            "Using PCM16 fallback (no Opus). "
            "This uses 5-8x more bandwidth. Install opuslib for better performance."
        )

    async def encode_pcm_to_base64_opus(self, pcm_audio: np.ndarray) -> list[str]:
        """Encode PCM as base64 (no actual Opus encoding)"""
        # Convert to int16
        if pcm_audio.dtype != np.int16:
            if pcm_audio.dtype in [np.float32, np.float64]:
                pcm_audio = np.clip(pcm_audio, -1.0, 1.0)
                pcm_audio = (pcm_audio * 32767).astype(np.int16)
            else:
                pcm_audio = pcm_audio.astype(np.int16)

        # Return as single base64 chunk (not as efficient as Opus frames)
        base64_pcm = base64.b64encode(pcm_audio.tobytes()).decode("utf-8")
        return [base64_pcm]

    async def decode_base64_opus_to_pcm(self, base64_data: str) -> np.ndarray:
        """Decode base64 PCM (no actual Opus decoding)"""
        pcm_bytes = base64.b64decode(base64_data)
        pcm_audio = np.frombuffer(pcm_bytes, dtype=np.int16)
        return pcm_audio


# ============================================================================
# Factory function
# ============================================================================


def create_audio_processor(
    sample_rate: int = SAMPLE_RATE,
) -> OpusStreamProcessor | PCM16Processor:
    """
    Create an audio processor (Opus if available, PCM16 fallback otherwise).

    Args:
        sample_rate: Sample rate in Hz

    Returns:
        Audio processor instance
    """
    if OPUS_AVAILABLE:
        return OpusStreamProcessor(sample_rate=sample_rate)
    else:
        return PCM16Processor(sample_rate=sample_rate)
