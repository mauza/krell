"""
Krell Backend - Configuration Management
"""

import yaml
from pathlib import Path
from typing import Optional


class Config:
    """Application configuration loaded from config.yaml"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = str(Path(__file__).parent / "config.yaml")

        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)

    @property
    def agentic_enabled(self) -> bool:
        return self._config.get("agentic", {}).get("enabled", False)

    @property
    def agentic_workflows(self) -> list:
        return self._config.get("agentic", {}).get("workflows", [])

    @property
    def embedding_provider(self) -> str:
        return self._config.get("embeddings", {}).get("provider", "openai")

    @property
    def embedding_model(self) -> str:
        return self._config.get("embeddings", {}).get("model", "text-embedding-ada-002")

    @property
    def vector_store_collection(self) -> str:
        return self._config.get("vector_store", {}).get(
            "collection_name", "krell_conversations"
        )

    @property
    def vector_store_path(self) -> str:
        return self._config.get("vector_store", {}).get(
            "persist_directory", "./data/chroma_db"
        )

    @property
    def database_path(self) -> str:
        return self._config.get("database", {}).get("path", "./data/krell.db")

    @property
    def server_host(self) -> str:
        return self._config.get("server", {}).get("host", "0.0.0.0")

    @property
    def server_port(self) -> int:
        return self._config.get("server", {}).get("port", 8000)

    @property
    def openai_api_key(self) -> str:
        """Get OpenAI API key from config or environment variable"""
        # First check config.yaml, then fall back to environment variable
        api_key = self._config.get("embeddings", {}).get("openai_api_key", "")
        if not api_key:
            import os

            api_key = os.getenv("OPENAI_API_KEY", "")
        return api_key

    # LLM configuration (OpenAI-compatible API)
    @property
    def llm_model(self) -> str:
        return self._config.get("llm", {}).get("model", "gpt-4o-mini")

    @property
    def llm_endpoint(self) -> str:
        return self._config.get("llm", {}).get("endpoint", "https://api.openai.com")

    @property
    def llm_openai_api_key(self) -> str:
        """Get OpenAI API key for LLM from config or environment"""
        # Prefer llm.openai_api_key, fallback to embeddings.openai_api_key, then env
        key = self._config.get("llm", {}).get("openai_api_key", "")
        if not key:
            key = self._config.get("embeddings", {}).get("openai_api_key", "")
        if not key:
            import os

            key = os.getenv("OPENAI_API_KEY", "")
        return key

    # TTS configuration - shared settings
    @property
    def tts_provider(self) -> str:
        return self._config.get("tts", {}).get("provider", "kyutai")

    @property
    def tts_endpoint(self) -> str:
        return self._config.get("tts", {}).get("endpoint", "http://localhost:8001")

    @property
    def tts_speed(self) -> float:
        return self._config.get("tts", {}).get("speed", 1.0)

    @property
    def tts_device(self) -> str:
        return self._config.get("tts", {}).get("device", "auto")

    @property
    def tts_chunk_size(self) -> int:
        return self._config.get("tts", {}).get("chunk_size", 4096)

    @property
    def tts_max_text_length(self) -> int:
        return self._config.get("tts", {}).get("max_text_length", 400)

    @property
    def tts_format(self) -> str:
        return self._config.get("tts", {}).get("format", "wav")

    @property
    def tts_mode(self) -> str:
        return self._config.get("tts", {}).get("mode", "direct")

    @property
    def tts_lang(self) -> str:
        return self._config.get("tts", {}).get("lang", "en-us")

    # TTS configuration - Kyutai-specific
    @property
    def tts_kyutai_model_path(self) -> str:
        return self._config.get("tts", {}).get("kyutai", {}).get("model_path", "")

    @property
    def tts_kyutai_voices_path(self) -> str:
        return self._config.get("tts", {}).get("kyutai", {}).get("voices_path", "")

    @property
    def tts_kyutai_voice(self) -> str:
        return self._config.get("tts", {}).get("kyutai", {}).get("voice", "tara")

    # Convenience properties that route to Kyutai settings
    @property
    def tts_model_path(self) -> str:
        return self.tts_kyutai_model_path

    @property
    def tts_voices_path(self) -> str:
        return self.tts_kyutai_voices_path

    @property
    def tts_voice(self) -> str:
        return self.tts_kyutai_voice

    # TTS Streaming configuration
    @property
    def tts_streaming_enabled(self) -> bool:
        return self._config.get("tts", {}).get("streaming", {}).get("enabled", True)

    @property
    def tts_streaming_min_sentence_length(self) -> int:
        return (
            self._config.get("tts", {})
            .get("streaming", {})
            .get("min_sentence_length", 20)
        )

    @property
    def tts_streaming_tool_pause_duration(self) -> float:
        return (
            self._config.get("tts", {})
            .get("streaming", {})
            .get("tool_pause_duration", 0.5)
        )


# Global config instance
config = Config()
