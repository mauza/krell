"""
Kyutai TTS Model Wrapper - PyTorch inference for low-latency TTS.

This module provides a wrapper around the moshi package for in-process text-to-speech
generation using Kyutai's TTS model.
"""

import os
import io
import asyncio
import logging
from typing import AsyncIterator, Optional
import wave

import numpy as np
import torch

logger = logging.getLogger(__name__)


class KyutaiModel:
    """
    Wrapper for Kyutai TTS model using PyTorch.

    This class provides:
    - Single model load at initialization (persistent in memory)
    - GPU acceleration support via PyTorch
    - Streaming audio generation
    - WAV format encoding
    """

    def __init__(
        self,
        model_path: str,
        voices_path: str,
        device: str = "auto",
    ):
        """
        Initialize Kyutai TTS model.

        Args:
            model_path: Path to model directory or HuggingFace repo name
            voices_path: Path to voices directory or HuggingFace repo name
            device: Device to use - "auto", "cuda", or "cpu"
        """
        self.model_path = model_path
        self.voices_path = voices_path
        self.device = self._resolve_device(device)
        self._model = None
        self._initialized = False
        self._sample_rate = 24000  # Kyutai TTS uses 24kHz

    def _resolve_device(self, device: str) -> str:
        """Resolve device string to actual device."""
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    def _initialize(self):
        """Initialize the Kyutai TTS model (lazy loading)."""
        if self._initialized:
            return

        logger.info(f"Loading Kyutai TTS model from {self.model_path}")
        logger.info(f"Using voices from {self.voices_path}")
        logger.info(f"Device: {self.device}")

        try:
            from moshi.models.loaders import CheckpointInfo
            from moshi.models.tts import TTSModel

            # Load model from HuggingFace repo or cache
            # The model_path should be a HuggingFace repo ID like "kyutai/tts-1.6b-en_fr"
            # or it will use the cached version from ~/.cache/huggingface/
            if os.path.isdir(self.model_path):
                # If it's a local directory, assume it was downloaded from HF
                # Use the default HF repo name which will use the cache
                logger.info(
                    "Local model directory detected, using HuggingFace cache (repo: kyutai/tts-1.6b-en_fr)"
                )
                checkpoint_info = CheckpointInfo.from_hf_repo("kyutai/tts-1.6b-en_fr")
            else:
                # Assume it's a HuggingFace repo ID
                checkpoint_info = CheckpointInfo.from_hf_repo(self.model_path)

            # Create TTSModel
            # Note: voice_repo parameter expects a HuggingFace repo ID
            # We'll use the default and resolve voice paths manually
            self._model = TTSModel.from_checkpoint_info(
                checkpoint_info,
                device=self.device,
            )
            self._sample_rate = self._model.mimi.sample_rate
            self._initialized = True
            logger.info(
                f"Kyutai TTS model loaded successfully on device={self.device} (sample_rate={self._sample_rate})"
            )
        except Exception as e:
            logger.error(f"Failed to load Kyutai TTS model: {e}")
            raise

    def warmup(self, voice: str = "expresso/ex03-ex01_happy_001_channel1_334s.wav"):
        """
        Warm up the model by generating a short audio sample.

        This pre-loads any JIT compilation or initialization overhead.

        Args:
            voice: Voice to use for warmup
        """
        if not self._initialized:
            self._initialize()

        logger.info("Warming up Kyutai TTS model...")
        try:
            # Generate very short audio to warm up the model
            _ = self.synthesize("Hello", voice=voice)
            logger.info("Kyutai TTS model warmed up successfully")
        except Exception as e:
            logger.warning(f"Model warmup failed: {e}")

    def _get_voice_path(self, voice: str):
        """
        Resolve voice name to full path.

        Args:
            voice: Voice name (relative path within voices directory)

        Returns:
            Full path to voice file (Path object)
        """
        from pathlib import Path

        if voice.endswith(".safetensors"):
            # Already a safetensors embedding file
            if os.path.isabs(voice):
                return Path(voice)
            return Path(self.voices_path) / voice

        # Use model's get_voice_path method if available
        if self._model is not None:
            try:
                return self._model.get_voice_path(voice)
            except Exception:
                pass

        # Fallback: construct path manually
        if os.path.isabs(voice):
            return Path(voice)
        return Path(self.voices_path) / voice

    def _numpy_to_wav_bytes(self, audio: np.ndarray, sample_rate: int) -> bytes:
        """
        Convert numpy audio array to WAV format bytes.

        Args:
            audio: Audio data as numpy array (float32, range [-1, 1])
            sample_rate: Sample rate of the audio

        Returns:
            WAV file as bytes
        """
        # Ensure audio is in int16 format
        if audio.dtype != np.int16:
            # Normalize to [-1, 1] if float
            if audio.dtype in [np.float32, np.float64]:
                audio = np.clip(audio, -1.0, 1.0)
                audio = (audio * 32767).astype(np.int16)
            else:
                audio = audio.astype(np.int16)

        # Create WAV file in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio.tobytes())

        return wav_buffer.getvalue()

    def synthesize(
        self,
        text: str,
        voice: str = "expresso/ex03-ex01_happy_001_channel1_334s.wav",
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> tuple[np.ndarray, int]:
        """
        Generate speech audio from text (non-streaming).

        This method generates the complete audio before returning.

        Args:
            text: Text to synthesize
            voice: Voice name to use (path relative to voices directory)
            speed: Speech speed (currently not implemented for Kyutai)
            lang: Language code (currently not used, model handles automatically)

        Returns:
            Tuple of (audio_array, sample_rate)
        """
        if not self._initialized:
            self._initialize()

        if not self._model:
            raise RuntimeError("Model not initialized")

        logger.debug(f"Synthesizing text (length={len(text)}, voice={voice})")

        # Prepare script entries
        entries = self._model.prepare_script([text], padding_between=1)

        # Get voice path
        voice_path = self._get_voice_path(voice)
        logger.debug(f"Using voice path: {voice_path}")

        # Create condition attributes with CFG coefficient
        condition_attributes = self._model.make_condition_attributes(
            [voice_path], cfg_coef=2.0
        )

        # Generate audio
        with torch.no_grad():
            result = self._model.generate([entries], [condition_attributes])

            # Decode frames to PCM
            with self._model.mimi.streaming(1):
                pcms = []
                for frame in result.frames[self._model.delay_steps :]:
                    if (frame != -1).all():
                        pcm = self._model.mimi.decode(frame[:, 1:, :]).cpu().numpy()
                        pcms.append(np.clip(pcm[0, 0], -1, 1))

        if pcms:
            audio = np.concatenate(pcms, axis=-1)
        else:
            audio = np.array([], dtype=np.float32)

        return audio, self._sample_rate

    async def synthesize_stream(
        self,
        text: str,
        voice: str = "expresso/ex03-ex01_happy_001_channel1_334s.wav",
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> AsyncIterator[bytes]:
        """
        Generate speech audio from text in streaming chunks.

        This method yields WAV audio data in chunks as they are generated,
        allowing for lower latency playback.

        Note: Kyutai's model generates frames that need to be accumulated
        and decoded together for proper audio output.

        Args:
            text: Text to synthesize
            voice: Voice name to use
            speed: Speech speed (currently not implemented for Kyutai)
            lang: Language code

        Yields:
            Chunks of WAV audio data as bytes
        """
        if not self._initialized:
            self._initialize()

        if not self._model:
            raise RuntimeError("Model not initialized")

        logger.debug(f"Streaming synthesis (length={len(text)}, voice={voice})")

        # For now, generate complete audio and yield in chunks
        # True streaming would require more complex frame-by-frame handling
        audio, sample_rate = await asyncio.to_thread(
            self.synthesize, text, voice, speed, lang
        )

        # Convert to WAV bytes
        wav_bytes = self._numpy_to_wav_bytes(audio, sample_rate)

        # Yield in chunks
        chunk_size = 8192
        for i in range(0, len(wav_bytes), chunk_size):
            yield wav_bytes[i : i + chunk_size]

    def get_available_voices(self) -> list[str]:
        """
        Get list of available voice names.

        Returns list of voice file paths relative to the voices directory.
        """
        voices = []
        if os.path.isdir(self.voices_path):
            for root, _dirs, files in os.walk(self.voices_path):
                for f in files:
                    if f.endswith((".wav", ".safetensors")):
                        rel_path = os.path.relpath(
                            os.path.join(root, f), self.voices_path
                        )
                        voices.append(rel_path)
        return sorted(voices)

    def get_supported_languages(self) -> list[str]:
        """Get list of supported language codes."""
        # Kyutai TTS 1.6b supports English and French
        return ["en", "fr"]
