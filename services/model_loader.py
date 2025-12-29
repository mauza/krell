"""Model loader utilities for downloading and verifying AI models."""

import os
import logging
from pathlib import Path
import json

# Import snapshot_download at module level for testability
try:
    from huggingface_hub import snapshot_download

    HAS_HF_HUB = True
except ImportError:
    snapshot_download = None  # type: ignore
    HAS_HF_HUB = False

logger = logging.getLogger(__name__)


def verify_model_files(model_path: str, voices_path: str) -> bool:
    """
    Verify that the required Kyutai TTS model and voice files exist.

    Args:
        model_path: Path to the Kyutai TTS model directory
        voices_path: Path to the Kyutai voices directory

    Returns:
        True if both directories exist and contain files, False otherwise
    """
    if not os.path.isdir(model_path):
        logger.info(
            f"Model directory does not exist or is not a directory: {model_path}"
        )
        return False

    if not os.path.isdir(voices_path):
        logger.info(
            f"Voices directory does not exist or is not a directory: {voices_path}"
        )
        return False

    model_files = [f for f in os.listdir(model_path) if not f.startswith(".")]
    if not model_files:
        logger.info(f"Model directory is empty: {model_path}")
        return False

    voice_files = [
        f
        for f in os.listdir(voices_path)
        if f.endswith(".wav") or f.endswith(".safetensors")
    ]
    if not voice_files:
        logger.info(f"No voice files found in voices directory: {voices_path}")
        return False

    logger.info(
        f"Model files verified: {len(model_files)} model files, {len(voice_files)} voice files"
    )
    return True


def download_kyutai_models(model_path: str, voices_path: str) -> bool:
    """
    Download Kyutai TTS models and voices from HuggingFace Hub.

    Args:
        model_path: Local path where the Kyutai TTS model should be downloaded
        voices_path: Local path where the Kyutai voices should be downloaded

    Returns:
        True if download succeeded, False otherwise
    """
    if not HAS_HF_HUB:
        logger.error(
            "huggingface_hub package not available. Install with: pip install huggingface_hub"
        )
        return False

    try:
        if not HAS_HF_HUB:
            raise ImportError("huggingface_hub package not available")

        logger.info("Starting Kyutai model downloads...")

        model_repo = "kyutai-moshi/moshi"  # Official repo from the package
        voices_repo = "kyutai/tts-voices"

        os.makedirs(model_path, exist_ok=True)
        logger.info(f"Downloading Kyutai TTS model from {model_repo} to {model_path}")

        snapshot_download(  # type: ignore
            repo_id=model_repo,
            local_dir=model_path,
            local_dir_use_symlinks=False,
        )

        os.makedirs(voices_path, exist_ok=True)
        logger.info(f"Downloading Kyutai voices from {voices_repo} to {voices_path}")

        snapshot_download(  # type: ignore
            repo_id=voices_repo,
            local_dir=voices_path,
            local_dir_use_symlinks=False,
        )

        logger.info("All Kyutai models downloaded successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to download Kyutai models: {e}")
        return False
