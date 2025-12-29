"""Tests for the model loader functionality."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock


def test_verify_model_files_returns_false_when_files_missing():
    """verify_model_files should return False when model files don't exist."""
    from services.model_loader import verify_model_files

    # Test with non-existent paths
    result = verify_model_files("/nonexistent/model", "/nonexistent/voices")

    assert result is False


def test_verify_model_files_returns_true_when_files_exist():
    """verify_model_files should return True when model files exist."""
    from services.model_loader import verify_model_files

    with patch("os.path.isdir") as mock_isdir:
        with patch("os.listdir") as mock_listdir:
            # Mock that both model and voices directories exist and have content
            mock_isdir.return_value = True
            mock_listdir.side_effect = [
                ["model_file.bin"],  # First call - model directory
                ["voice_file.wav"],  # Second call - voices directory
            ]

            result = verify_model_files("/existing/model", "/existing/voices")

            assert result is True
            assert mock_isdir.call_count == 2
            assert mock_listdir.call_count == 2


def test_verify_model_files_returns_false_when_voices_empty():
    """verify_model_files should return False when voices directory is empty."""
    from services.model_loader import verify_model_files

    with patch("os.path.isdir") as mock_isdir:
        with patch("os.listdir") as mock_listdir:
            # Mock that both directories exist but voices has no .wav/.safetensors files
            mock_isdir.return_value = True
            mock_listdir.side_effect = [
                ["model_file.bin"],  # First call - model directory has files
                [
                    "readme.txt",
                    "config.json",
                ],  # Second call - voices directory has no voice files
            ]

            result = verify_model_files("/existing/model", "/existing/voices")

            assert result is False


def test_download_kyutai_models_downloads_from_huggingface():
    """download_kyutai_models should download from correct HuggingFace repos."""
    from services.model_loader import download_kyutai_models

    # Mock the HAS_HF_HUB flag to True
    with patch("services.model_loader.HAS_HF_HUB", True):
        # Import and patch snapshot_download at runtime
        with patch("services.model_loader.snapshot_download") as mock_download:
            with patch("os.makedirs") as mock_makedirs:
                # Configure mock for snapshot_download to return the target directory
                mock_download.side_effect = lambda **kwargs: kwargs["local_dir"]

                # Test downloading
                result = download_kyutai_models(
                    "/models/kyutai-tts", "/models/kyutai-voices"
                )

                # Verify it was called for both model and voices
                assert mock_download.call_count == 2
                assert result is True
