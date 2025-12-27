"""
TTS Service - Streams audio from Kyutai TTS.

Supports direct in-process inference for lowest latency.
The model is kept loaded in memory for fast generation.
"""

from typing import AsyncIterator, Dict, Optional, List
import aiohttp
import asyncio
import time
import socket
import subprocess
import tempfile
import os
import logging
import re
import numpy as np
import io
import wave

try:
    from services.kyutai_model import KyutaiModel
except ImportError:
    KyutaiModel = None

logger = logging.getLogger(__name__)


def clean_text_for_tts(text: str) -> str:
    """
    Clean text to make it more natural for TTS by removing markdown and special characters.

    This function:
    1. Removes markdown syntax (**bold**, *italic*, __underline__, etc.)
    2. Removes or normalizes special characters that shouldn't be spoken
    3. Cleans up lists and other formatting
    4. Keeps natural punctuation for speech rhythm

    Args:
        text: Raw text that may contain markdown and special characters

    Returns:
        Cleaned text suitable for TTS
    """
    if not text:
        return ""

    # Remove markdown bold (**text** or __text__)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)

    # Remove markdown italic (*text* or _text_)
    # Be careful not to remove single asterisks used as bullet points
    text = re.sub(r"(?<!\*)\*([^*_\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", text)

    # Remove markdown links [text](url) - keep just the text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # Remove markdown images ![alt](url)
    text = re.sub(r"!\[[^\]]*\]\([^\)]+\)", "", text)

    # Remove markdown code blocks (```code```)
    text = re.sub(r"```[^`]*```", "", text, flags=re.MULTILINE)

    # Remove inline code (`code`)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Remove markdown headers (# Header)
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)

    # Clean up markdown lists: replace "- " or "* " at line start with nothing
    text = re.sub(r"(?m)^\s*[-*]\s+", "", text)

    # Clean up numbered lists: "1. " at line start
    text = re.sub(r"(?m)^\s*\d+\.\s+", "", text)

    # Remove blockquotes (> quote)
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)

    # Remove horizontal rules (--- or ***)
    text = re.sub(r"^[-*_]{3,}$", "", text, flags=re.MULTILINE)

    # Remove excessive whitespace and newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    # Remove special characters that shouldn't be spoken
    # Keep basic punctuation: . , ! ? : ; - (for pauses)
    text = re.sub(r'[^\w\s.,!?;:\-()\'"\[\]]', " ", text)

    # Clean up multiple spaces
    text = re.sub(r"\s+", " ", text)

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def chunk_text_by_sentences(text: str, max_length: int = 500) -> List[str]:
    """
    Split text into chunks by sentences, respecting max_length.

    IMPORTANT: This function NEVER splits within a sentence. If a single sentence
    exceeds max_length, it will be kept as a single chunk to avoid awkward pauses
    in TTS output.

    This function:
    1. Cleans text using clean_text_for_tts()
    2. Splits text by sentence boundaries (., !, ?, etc.)
    3. Groups sentences together until max_length would be exceeded
    4. Keeps sentences intact (never splits mid-sentence)

    Args:
        text: The text to chunk
        max_length: Target maximum length per chunk (advisory, not strict)

    Returns:
        List of text chunks (each containing one or more complete sentences)
    """
    if not text or not text.strip():
        return []

    # Clean the text first
    text = clean_text_for_tts(text)

    if not text:
        return []

    # Split by sentence endings while preserving the delimiter
    # This regex splits on: . ! ? followed by space or newline/end of string
    # Pattern explained:
    # - (?<=[.!?]) - lookbehind for sentence ending punctuation
    # - \s+ - one or more whitespace characters
    # - (?=[A-Z]) - lookahead for capital letter (start of next sentence)
    # OR
    # - (?<=[.!?])$ - sentence ending at end of string
    sentence_pattern = r"(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])(?=\n)|(?<=[.!?])$"
    sentences = re.split(sentence_pattern, text)

    # Clean up sentences and filter empty ones
    sentences = [s.strip() for s in sentences if s.strip()]

    # If no proper sentences found, treat the whole text as one chunk
    if len(sentences) == 0:
        return [text] if text.strip() else []

    # If only one sentence, return it as-is (even if longer than max_length)
    if len(sentences) == 1:
        return [sentences[0]]

    # Group sentences into chunks
    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        # If this is the first sentence in the chunk, always add it
        if not current_chunk:
            current_chunk.append(sentence)
            current_length = sentence_len
        # Check if adding this sentence would exceed max_length
        elif current_length + sentence_len + 1 > max_length:
            # Save current chunk and start new one with this sentence
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_length = sentence_len
        else:
            # Add sentence to current chunk
            current_chunk.append(sentence)
            current_length += sentence_len + 1  # +1 for space

    # Add remaining chunk
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    # Log warning if any chunk significantly exceeds max_length
    for i, chunk in enumerate(chunks):
        if len(chunk) > max_length * 1.5:
            logger.warning(
                f"Chunk {i + 1} is {len(chunk)} chars (target: {max_length}). "
                "Consider using shorter sentences or increasing max_text_length."
            )

    return chunks


class TTSService:
    def __init__(
        self,
        provider: str,
        endpoint: str,
        voice: str,
        fmt: str = "wav",
        model_path: str = "",
        voices_path: str = "",
        device: str = "auto",
        enable_direct: bool = False,
    ):
        self.provider = provider
        self.endpoint = endpoint.rstrip("/")
        self.voice = voice
        self.fmt = fmt
        self.model_path = model_path
        self.voices_path = voices_path
        self.device = device
        self._kyutai_model = None

        # Initialize Kyutai TTS model
        if model_path and voices_path and KyutaiModel is not None:
            try:
                logger.info("Initializing Kyutai TTS model...")
                self._kyutai_model = KyutaiModel(
                    model_path=model_path, voices_path=voices_path, device=device
                )
                # Warm up the model
                self._kyutai_model.warmup(voice=voice)
                logger.info("Kyutai TTS model initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Kyutai TTS model: {e}")
                self._kyutai_model = None

    async def stream_tts_chunked(
        self,
        text: str,
        max_text_length: int = 500,
        voice: Optional[str] = None,
        lang: str = "en-us",
        speed: float = 1.0,
    ) -> AsyncIterator[bytes]:
        """
        Stream TTS audio for long text by chunking it into smaller segments.

        This method:
        1. Splits text into chunks that respect max_text_length
        2. Generates audio for each chunk separately
        3. Concatenates audio at numpy level
        4. Streams the combined audio as a single proper WAV file

        Args:
            text: Text to synthesize (can be any length)
            max_text_length: Maximum characters per TTS chunk
            voice: Voice name (uses default if None)
            lang: Language code
            speed: Speech speed (0.5 to 2.0)

        Yields:
            Audio data chunks as bytes (WAV format)
        """
        async for chunk in self._stream_tts_chunked_kyutai(
            text=text,
            max_text_length=max_text_length,
            voice=voice,
            lang=lang,
            speed=speed,
        ):
            yield chunk

    async def _stream_tts_chunked_kyutai(
        self,
        text: str,
        max_text_length: int = 500,
        voice: Optional[str] = None,
        lang: str = "en-us",
        speed: float = 1.0,
    ) -> AsyncIterator[bytes]:
        """
        Stream TTS audio using Kyutai model with sentence-based chunking.
        """
        if not text or not text.strip():
            return

        if not self._kyutai_model:
            raise RuntimeError(
                "Kyutai TTS model not initialized. "
                "Please check model paths and initialization."
            )

        # Chunk the text
        text_chunks = chunk_text_by_sentences(text, max_length=max_text_length)
        logger.info(f"Split text into {len(text_chunks)} chunks for Kyutai TTS")

        if not text_chunks:
            return

        chosen_voice = voice or self.voice
        all_audio_data = []
        sample_rate = None

        # Generate audio for each text chunk
        for i, text_chunk in enumerate(text_chunks):
            logger.debug(
                f"Generating Kyutai audio for chunk {i + 1}/{len(text_chunks)}: {len(text_chunk)} chars"
            )

            audio_array, rate = await asyncio.to_thread(
                self._kyutai_model.synthesize,
                text=text_chunk,
                voice=chosen_voice,
                speed=speed,
                lang=lang,
            )

            all_audio_data.append(audio_array)
            if sample_rate is None:
                sample_rate = rate

        # Concatenate all audio arrays
        if not all_audio_data:
            return

        logger.debug(f"Concatenating {len(all_audio_data)} Kyutai audio chunks")
        combined_audio = np.concatenate(all_audio_data)

        # Convert to int16 if needed
        if combined_audio.dtype != np.int16:
            if combined_audio.dtype in [np.float32, np.float64]:
                combined_audio = np.clip(combined_audio, -1.0, 1.0)
                combined_audio = (combined_audio * 32767).astype(np.int16)
            else:
                combined_audio = combined_audio.astype(np.int16)

        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate or 24000)
            wav_file.writeframes(combined_audio.tobytes())

        # Stream the complete WAV file in chunks
        wav_data = wav_buffer.getvalue()
        logger.info(f"Generated combined Kyutai audio: {len(wav_data)} bytes")

        chunk_size = 8192
        for i in range(0, len(wav_data), chunk_size):
            yield wav_data[i : i + chunk_size]
