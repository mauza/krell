"""
Protocol Definitions - Interface contracts for Krell components.

This module uses Python's Protocol classes to define interfaces that enable:
- Loose coupling between components
- Easy testing with mocks
- Runtime provider selection
- Clear contracts between components

Usage:
    from core.protocols import LLMProvider, TTSProvider

    class MyLLMService(LLMProvider):
        async def generate(self, messages, **kwargs) -> str:
            ...

    # Type checking works, but no inheritance required
    def process(llm: LLMProvider) -> None:
        response = await llm.generate(messages)
"""

from typing import (
    Any,
    AsyncGenerator,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    TypeVar,
    runtime_checkable,
)

import numpy as np
from numpy.typing import NDArray


# =============================================================================
# Service Lifecycle Protocol
# =============================================================================


@runtime_checkable
class ServiceWithStartup(Protocol):
    """
    Protocol for services that require initialization.

    Used by service discovery to verify service health before use.
    """

    async def start_up(self) -> None:
        """
        Initialize the service connection.

        Should raise an exception if the service is not ready.
        """
        ...


@runtime_checkable
class ServiceWithShutdown(Protocol):
    """Protocol for services that require cleanup."""

    async def shutdown(self) -> None:
        """Clean up service resources."""
        ...


# =============================================================================
# LLM Provider Protocol
# =============================================================================


@runtime_checkable
class LLMProvider(Protocol):
    """
    Protocol for LLM service providers.

    Implementations can wrap OpenAI, Ollama, Anthropic, or any other LLM API.
    """

    @property
    def model(self) -> str:
        """The model identifier being used."""
        ...

    @property
    def endpoint(self) -> str:
        """The API endpoint URL."""
        ...

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate a response from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific options

        Returns:
            Generated text response

        Raises:
            LLMConnectionError: Cannot reach the service
            LLMRateLimitError: Rate limited
            LLMAuthenticationError: Invalid credentials
        """
        ...

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming response from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific options

        Yields:
            Text chunks as they're generated

        Raises:
            LLMConnectionError: Cannot reach the service
            LLMRateLimitError: Rate limited
            LLMAuthenticationError: Invalid credentials
        """
        ...
        yield ""  # Required for generator type


# =============================================================================
# TTS Provider Protocol
# =============================================================================


@runtime_checkable
class TTSProvider(Protocol):
    """
    Protocol for Text-to-Speech service providers.

    Implementations can wrap Kyutai, OpenAI TTS, ElevenLabs, etc.
    """

    @property
    def provider(self) -> str:
        """Provider name (e.g., 'kyutai', 'openai', 'elevenlabs')."""
        ...

    @property
    def voice(self) -> str:
        """Default voice identifier."""
        ...

    async def synthesize(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        speed: float = 1.0,
        lang: str = "en-us",
        **kwargs: Any,
    ) -> Tuple[NDArray[np.int16], int]:
        """
        Synthesize speech from text.

        Args:
            text: Text to synthesize
            voice: Voice identifier (uses default if None)
            speed: Speech speed multiplier (0.5 to 2.0)
            lang: Language code
            **kwargs: Additional provider-specific options

        Returns:
            Tuple of (audio_array, sample_rate)
            - audio_array: int16 numpy array of audio samples
            - sample_rate: Sample rate in Hz (e.g., 24000)

        Raises:
            TTSModelNotFoundError: Model not loaded
            TTSVoiceNotFoundError: Voice not available
            TTSSynthesisError: Synthesis failed
        """
        ...

    async def synthesize_stream(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        speed: float = 1.0,
        lang: str = "en-us",
        chunk_size: int = 8192,
        **kwargs: Any,
    ) -> AsyncIterator[bytes]:
        """
        Stream synthesized speech as audio bytes.

        Args:
            text: Text to synthesize
            voice: Voice identifier (uses default if None)
            speed: Speech speed multiplier
            lang: Language code
            chunk_size: Size of audio chunks to yield
            **kwargs: Additional provider-specific options

        Yields:
            Audio data chunks as bytes (WAV format)

        Raises:
            TTSModelNotFoundError: Model not loaded
            TTSVoiceNotFoundError: Voice not available
            TTSSynthesisError: Synthesis failed
        """
        ...


@runtime_checkable
class VoiceProvider(Protocol):
    """Protocol for voice management."""

    async def list_voices(self) -> List[Dict[str, Any]]:
        """
        List available voices.

        Returns:
            List of voice info dicts with 'id', 'name', 'language', etc.
        """
        ...

    async def get_voice(self, voice_id: str) -> Optional[Dict[str, Any]]:
        """
        Get details for a specific voice.

        Args:
            voice_id: Voice identifier

        Returns:
            Voice info dict or None if not found
        """
        ...


# =============================================================================
# Storage Provider Protocol
# =============================================================================


@runtime_checkable
class StorageProvider(Protocol):
    """
    Protocol for data persistence.

    Implementations can use SQLite, PostgreSQL, or other backends.
    """

    async def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        ...

    async def set(self, key: str, value: Any) -> None:
        """Set a value by key."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a value by key."""
        ...

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        ...


@runtime_checkable
class ConversationStorage(Protocol):
    """Protocol for conversation persistence."""

    async def create_conversation(self, title: str) -> str:
        """Create a new conversation and return its ID."""
        ...

    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation by ID."""
        ...

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Add a message to a conversation and return the message ID."""
        ...

    async def get_conversation_messages(
        self, conversation_id: str
    ) -> List[Dict[str, Any]]:
        """Get all messages for a conversation."""
        ...


# =============================================================================
# Cache Provider Protocol
# =============================================================================

T = TypeVar("T")


@runtime_checkable
class CacheProvider(Protocol[T]):
    """
    Protocol for caching.

    Implementations can use Redis, in-memory dict, or other backends.
    """

    def get(self, key: str) -> Optional[T]:
        """Get a cached value. Returns None if not found or expired."""
        ...

    def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """
        Set a cached value.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        ...

    def delete(self, key: str) -> None:
        """Delete a cached value."""
        ...

    def cleanup(self) -> None:
        """Remove expired entries (for implementations that need it)."""
        ...


# =============================================================================
# Tool/Plugin Provider Protocol
# =============================================================================


@runtime_checkable
class ToolProvider(Protocol):
    """Protocol for tool/plugin providers."""

    @property
    def name(self) -> str:
        """Tool name."""
        ...

    @property
    def description(self) -> str:
        """Tool description for LLM context."""
        ...

    async def execute(self, **kwargs: Any) -> Any:
        """
        Execute the tool with given parameters.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Tool execution result
        """
        ...


# =============================================================================
# Agent Protocol
# =============================================================================


@runtime_checkable
class AgentProvider(Protocol):
    """Protocol for AI agents."""

    async def chat(
        self,
        conversation_id: Optional[str],
        user_message: str,
    ) -> Dict[str, Any]:
        """
        Generate a response to a user message.

        Args:
            conversation_id: Conversation ID or None for new conversation
            user_message: User's message

        Returns:
            Dict with 'response', 'conversation_id', 'tool_calls', etc.
        """
        ...

    async def chat_stream(
        self,
        conversation_id: Optional[str],
        user_message: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate a streaming response to a user message.

        Args:
            conversation_id: Conversation ID or None for new conversation
            user_message: User's message

        Yields:
            Event dicts with 'type' field ('text', 'tool_call', 'done', etc.)
        """
        ...
        yield {}  # Required for generator type


# =============================================================================
# Recorder Protocol
# =============================================================================


@runtime_checkable
class RecorderProvider(Protocol):
    """Protocol for event recording."""

    async def record(self, event: Dict[str, Any]) -> None:
        """Record an event."""
        ...

    async def shutdown(self, keep_recording: bool = True) -> None:
        """Shutdown the recorder."""
        ...


# =============================================================================
# Metrics Protocol
# =============================================================================


@runtime_checkable
class MetricsProvider(Protocol):
    """Protocol for metrics collection."""

    def increment(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        ...

    def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Observe a histogram/summary value."""
        ...

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge value."""
        ...
