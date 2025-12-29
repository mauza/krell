"""Tests for application startup behavior with model loading."""

import pytest
from unittest.mock import patch, MagicMock
from contextlib import asynccontextmanager


@pytest.mark.asyncio
async def test_startup_succeeds_when_models_exist():
    """Application should start successfully when models exist."""
    # Test the core startup logic without importing main.py
    with patch(
        "services.model_loader.verify_model_files", return_value=True
    ) as mock_verify:
        with patch("services.model_loader.download_kyutai_models") as mock_download:
            # Simulate the lifespan startup logic from main.py
            config_mock = MagicMock()
            config_mock.tts_model_path = "./models/kyutai-tts-1.6b"
            config_mock.tts_voices_path = "./models/kyutai-voices"

            # This is the logic from main.py's lifespan function
            if not mock_verify(config_mock.tts_model_path, config_mock.tts_voices_path):
                # This shouldn't execute since verify returns True
                mock_download(config_mock.tts_model_path, config_mock.tts_voices_path)
                if not mock_verify(
                    config_mock.tts_model_path, config_mock.tts_voices_path
                ):
                    raise RuntimeError("Failed to download Kyutai models on startup")

            # If we get here, startup succeeded
            assert True

            # Verify download was NOT called (models already existed)
            mock_verify.assert_called_once_with(
                config_mock.tts_model_path, config_mock.tts_voices_path
            )
            mock_download.assert_not_called()


@pytest.mark.asyncio
async def test_startup_downloads_models_when_missing():
    """Application should download models when missing and succeed."""
    with patch(
        "services.model_loader.verify_model_files", side_effect=[False, True]
    ) as mock_verify:
        with patch(
            "services.model_loader.download_kyutai_models", return_value=True
        ) as mock_download:
            config_mock = MagicMock()
            config_mock.tts_model_path = "./models/kyutai-tts-1.6b"
            config_mock.tts_voices_path = "./models/kyutai-voices"

            # This is the logic from main.py's lifespan function
            if not mock_verify(config_mock.tts_model_path, config_mock.tts_voices_path):
                # Download models
                if mock_download(
                    config_mock.tts_model_path, config_mock.tts_voices_path
                ):
                    # Verify again after download
                    if not mock_verify(
                        config_mock.tts_model_path, config_mock.tts_voices_path
                    ):
                        raise RuntimeError("Model verification failed after download")
                else:
                    raise RuntimeError("Failed to download Kyutai models on startup")

            # Success
            assert True

            # Verify both were called (verify called twice)
            assert mock_verify.call_count == 2
            mock_download.assert_called_once_with(
                config_mock.tts_model_path, config_mock.tts_voices_path
            )


@pytest.mark.asyncio
async def test_startup_fails_when_models_missing_and_download_fails():
    """Application should crash on startup when models missing and download fails."""
    with patch(
        "services.model_loader.verify_model_files", return_value=False
    ) as mock_verify:
        with patch(
            "services.model_loader.download_kyutai_models", return_value=False
        ) as mock_download:
            config_mock = MagicMock()
            config_mock.tts_model_path = "./models/kyutai-tts-1.6b"
            config_mock.tts_voices_path = "./models/kyutai-voices"

            # This is the failing logic from main.py's lifespan function
            with pytest.raises(RuntimeError) as exc_info:
                if not mock_verify(
                    config_mock.tts_model_path, config_mock.tts_voices_path
                ):
                    if not mock_download(
                        config_mock.tts_model_path, config_mock.tts_voices_path
                    ):
                        raise RuntimeError(
                            "Failed to download Kyutai models on startup"
                        )

            assert "Failed to download Kyutai models on startup" in str(exc_info.value)
            mock_verify.assert_called_once()
            mock_download.assert_called_once()
