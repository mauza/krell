"""
Audio Codec Utilities - Multi-format audio encoding for streaming.

This module provides audio encoding/decoding for:
- WAV: Uncompressed, maximum compatibility
- Opus: High compression (8x smaller), optimal for streaming
- PCM: Raw audio for processing

Opus is preferred for low-latency streaming due to:
- Much smaller packets (8x compression)
- Built-in error resilience
- Designed for real-time communication

Usage:
    from core.audio_codec import AudioCodec, encode_audio, decode_audio

    # Encode audio
    wav_bytes = encode_audio(audio_array, sample_rate, format="wav")
    opus_bytes = encode_audio(audio_array, sample_rate, format="opus")

    # Decode audio
    audio_array, sample_rate = decode_audio(opus_bytes, format="opus")

    # Using the codec class
    codec = AudioCodec(format="opus", sample_rate=24000)
    encoded = codec.encode(audio_array)
    decoded = codec.decode(encoded)
"""

import io
import logging
import wave
from enum import Enum
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Try to import opus encoder
try:
    import opuslib

    OPUS_AVAILABLE = True
except ImportError:
    OPUS_AVAILABLE = False
    logger.info("opuslib not available - Opus encoding disabled")


class AudioFormat(str, Enum):
    """Supported audio formats."""

    WAV = "wav"
    OPUS = "opus"
    PCM = "pcm"


# Standard sample rates
SAMPLE_RATE_24K = 24000  # Kyutai TTS output
SAMPLE_RATE_16K = 16000  # Common for STT
SAMPLE_RATE_48K = 48000  # Opus native


def encode_wav(audio_data: np.ndarray, sample_rate: int) -> bytes:
    """
    Encode audio to WAV format.

    Args:
        audio_data: Audio samples (int16 or float32)
        sample_rate: Sample rate in Hz

    Returns:
        Complete WAV file as bytes
    """
    # Ensure int16
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


def decode_wav(wav_bytes: bytes) -> Tuple[np.ndarray, int]:
    """
    Decode WAV to audio array.

    Args:
        wav_bytes: WAV file bytes

    Returns:
        Tuple of (audio_array, sample_rate)
    """
    wav_buffer = io.BytesIO(wav_bytes)
    with wave.open(wav_buffer, "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        n_channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        n_frames = wav_file.getnframes()

        raw_data = wav_file.readframes(n_frames)

    # Convert to numpy
    if sample_width == 2:
        audio_data = np.frombuffer(raw_data, dtype=np.int16)
    elif sample_width == 1:
        audio_data = np.frombuffer(raw_data, dtype=np.uint8).astype(np.int16)
        audio_data = (audio_data - 128) * 256
    else:
        raise ValueError(f"Unsupported sample width: {sample_width}")

    # Convert stereo to mono if needed
    if n_channels == 2:
        audio_data = audio_data.reshape(-1, 2).mean(axis=1).astype(np.int16)

    return audio_data, sample_rate


def encode_opus(
    audio_data: np.ndarray,
    sample_rate: int,
    bitrate: int = 24000,
    frame_duration_ms: int = 20,
) -> bytes:
    """
    Encode audio to Opus format.

    Opus provides ~8x compression over WAV while maintaining quality.
    Optimized for voice audio at low latencies.

    Args:
        audio_data: Audio samples (int16 or float32)
        sample_rate: Sample rate (will be resampled to 48000 if different)
        bitrate: Target bitrate in bps (default 24000 = 24kbps)
        frame_duration_ms: Frame duration (10, 20, 40, 60ms)

    Returns:
        Opus-encoded bytes

    Raises:
        ImportError: If opuslib is not installed
    """
    if not OPUS_AVAILABLE:
        raise ImportError(
            "opuslib is required for Opus encoding. Install with: pip install opuslib"
        )

    # Ensure int16
    if audio_data.dtype != np.int16:
        if audio_data.dtype in [np.float32, np.float64]:
            audio_data = np.clip(audio_data, -1.0, 1.0)
            audio_data = (audio_data * 32767).astype(np.int16)
        else:
            audio_data = audio_data.astype(np.int16)

    # Resample to 48kHz if needed (Opus native rate)
    if sample_rate != SAMPLE_RATE_48K:
        audio_data = _resample(audio_data, sample_rate, SAMPLE_RATE_48K)

    # Create encoder
    encoder = opuslib.Encoder(SAMPLE_RATE_48K, 1, opuslib.APPLICATION_VOIP)
    encoder.bitrate = bitrate

    # Frame size in samples
    frame_size = int(SAMPLE_RATE_48K * frame_duration_ms / 1000)

    # Encode in frames
    output_frames = []
    for i in range(0, len(audio_data), frame_size):
        frame = audio_data[i : i + frame_size]

        # Pad last frame if needed
        if len(frame) < frame_size:
            frame = np.pad(frame, (0, frame_size - len(frame)), mode="constant")

        encoded = encoder.encode(frame.tobytes(), frame_size)
        output_frames.append(encoded)

    # Combine frames with length prefixes for proper decoding
    output = io.BytesIO()
    for frame in output_frames:
        # Write 2-byte length prefix
        output.write(len(frame).to_bytes(2, "little"))
        output.write(frame)

    return output.getvalue()


def decode_opus(opus_bytes: bytes, sample_rate: int = SAMPLE_RATE_24K) -> np.ndarray:
    """
    Decode Opus to audio array.

    Args:
        opus_bytes: Opus-encoded bytes
        sample_rate: Target sample rate (will be resampled from 48000)

    Returns:
        Audio samples as int16 numpy array
    """
    if not OPUS_AVAILABLE:
        raise ImportError(
            "opuslib is required for Opus decoding. Install with: pip install opuslib"
        )

    decoder = opuslib.Decoder(SAMPLE_RATE_48K, 1)

    # Read frames
    input_buffer = io.BytesIO(opus_bytes)
    output_frames = []

    while True:
        length_bytes = input_buffer.read(2)
        if len(length_bytes) < 2:
            break

        frame_length = int.from_bytes(length_bytes, "little")
        frame_data = input_buffer.read(frame_length)
        if len(frame_data) < frame_length:
            break

        # Decode frame (20ms = 960 samples at 48kHz)
        decoded = decoder.decode(frame_data, 960)
        output_frames.append(np.frombuffer(decoded, dtype=np.int16))

    if not output_frames:
        return np.array([], dtype=np.int16)

    audio_data = np.concatenate(output_frames)

    # Resample if needed
    if sample_rate != SAMPLE_RATE_48K:
        audio_data = _resample(audio_data, SAMPLE_RATE_48K, sample_rate)

    return audio_data


def _resample(audio_data: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    """
    Simple linear resampling.

    For production use, consider using scipy.signal.resample or librosa.

    Args:
        audio_data: Audio samples
        from_rate: Original sample rate
        to_rate: Target sample rate

    Returns:
        Resampled audio
    """
    if from_rate == to_rate:
        return audio_data

    ratio = to_rate / from_rate
    output_length = int(len(audio_data) * ratio)

    # Linear interpolation
    x_old = np.arange(len(audio_data))
    x_new = np.linspace(0, len(audio_data) - 1, output_length)

    resampled = np.interp(x_new, x_old, audio_data.astype(np.float64))
    return resampled.astype(np.int16)


def encode_audio(
    audio_data: np.ndarray,
    sample_rate: int,
    format: str = "wav",
    **kwargs,
) -> bytes:
    """
    Encode audio to specified format.

    Args:
        audio_data: Audio samples
        sample_rate: Sample rate in Hz
        format: Output format ("wav", "opus", "pcm")
        **kwargs: Format-specific options

    Returns:
        Encoded audio bytes
    """
    format_lower = format.lower()

    if format_lower == "wav":
        return encode_wav(audio_data, sample_rate)
    elif format_lower == "opus":
        return encode_opus(audio_data, sample_rate, **kwargs)
    elif format_lower == "pcm":
        # Ensure int16
        if audio_data.dtype != np.int16:
            if audio_data.dtype in [np.float32, np.float64]:
                audio_data = np.clip(audio_data, -1.0, 1.0)
                audio_data = (audio_data * 32767).astype(np.int16)
            else:
                audio_data = audio_data.astype(np.int16)
        return audio_data.tobytes()
    else:
        raise ValueError(f"Unsupported format: {format}")


def decode_audio(
    audio_bytes: bytes,
    format: str,
    sample_rate: Optional[int] = None,
) -> Tuple[np.ndarray, int]:
    """
    Decode audio from specified format.

    Args:
        audio_bytes: Encoded audio
        format: Input format ("wav", "opus", "pcm")
        sample_rate: Sample rate (required for pcm/opus)

    Returns:
        Tuple of (audio_array, sample_rate)
    """
    format_lower = format.lower()

    if format_lower == "wav":
        return decode_wav(audio_bytes)
    elif format_lower == "opus":
        if sample_rate is None:
            sample_rate = SAMPLE_RATE_24K
        return decode_opus(audio_bytes, sample_rate), sample_rate
    elif format_lower == "pcm":
        if sample_rate is None:
            sample_rate = SAMPLE_RATE_24K
        return np.frombuffer(audio_bytes, dtype=np.int16), sample_rate
    else:
        raise ValueError(f"Unsupported format: {format}")


class AudioCodec:
    """
    Audio codec wrapper for consistent encoding/decoding.

    Usage:
        codec = AudioCodec(format="opus", sample_rate=24000)
        encoded = codec.encode(audio_array)
        decoded = codec.decode(encoded)
    """

    def __init__(
        self,
        format: str = "wav",
        sample_rate: int = SAMPLE_RATE_24K,
        bitrate: int = 24000,
    ):
        """
        Initialize codec.

        Args:
            format: Audio format ("wav", "opus", "pcm")
            sample_rate: Sample rate in Hz
            bitrate: Target bitrate for lossy formats
        """
        self.format = format.lower()
        self.sample_rate = sample_rate
        self.bitrate = bitrate

        if self.format == "opus" and not OPUS_AVAILABLE:
            logger.warning("Opus not available, falling back to WAV")
            self.format = "wav"

    def encode(self, audio_data: np.ndarray) -> bytes:
        """Encode audio to configured format."""
        kwargs = {}
        if self.format == "opus":
            kwargs["bitrate"] = self.bitrate
        return encode_audio(audio_data, self.sample_rate, self.format, **kwargs)

    def decode(self, audio_bytes: bytes) -> np.ndarray:
        """Decode audio from configured format."""
        audio, _ = decode_audio(audio_bytes, self.format, self.sample_rate)
        return audio

    @property
    def mime_type(self) -> str:
        """Get MIME type for the format."""
        if self.format == "wav":
            return "audio/wav"
        elif self.format == "opus":
            return "audio/opus"
        elif self.format == "pcm":
            return "audio/pcm"
        return "application/octet-stream"

    @property
    def is_opus_available(self) -> bool:
        """Check if Opus encoding is available."""
        return OPUS_AVAILABLE


def get_optimal_codec(prefer_opus: bool = True) -> AudioCodec:
    """
    Get the optimal audio codec based on availability.

    Args:
        prefer_opus: Prefer Opus if available

    Returns:
        Configured AudioCodec instance
    """
    if prefer_opus and OPUS_AVAILABLE:
        return AudioCodec(format="opus")
    return AudioCodec(format="wav")
