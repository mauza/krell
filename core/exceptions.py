"""
Krell Exception Hierarchy - Domain-specific exceptions for different failure modes.

This module defines a structured exception hierarchy that enables:
- Appropriate handling for different failure modes
- Better error messages for users
- Retry logic for transient failures
- Clean exception handling code
"""

from typing import Any


class KrellError(Exception):
    """Base exception for all Krell errors."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(message)
        self.message = message
        self.details = details


# =============================================================================
# LLM Errors
# =============================================================================


class LLMError(KrellError):
    """Base exception for LLM-related failures."""

    pass


class LLMConnectionError(LLMError):
    """Cannot reach the LLM service."""

    def __init__(self, endpoint: str, cause: Exception | None = None):
        self.endpoint = endpoint
        self.cause = cause
        message = f"Cannot connect to LLM at {endpoint}"
        if cause:
            message += f": {cause}"
        super().__init__(message)


class LLMRateLimitError(LLMError):
    """LLM service rate limited the request. Retry later."""

    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after
        message = "LLM rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after}s"
        super().__init__(message)


class LLMContextOverflowError(LLMError):
    """Context window exceeded."""

    def __init__(self, token_count: int | None = None, max_tokens: int | None = None):
        self.token_count = token_count
        self.max_tokens = max_tokens
        message = "Context window exceeded"
        if token_count and max_tokens:
            message += f" ({token_count}/{max_tokens} tokens)"
        super().__init__(message)


class LLMAuthenticationError(LLMError):
    """Invalid or missing API key."""

    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        super().__init__(f"Authentication failed for LLM at {endpoint}")


class LLMModelNotFoundError(LLMError):
    """Requested model not available."""

    def __init__(self, model: str, endpoint: str):
        self.model = model
        self.endpoint = endpoint
        super().__init__(f"Model '{model}' not found at {endpoint}")


# =============================================================================
# TTS Errors
# =============================================================================


class TTSError(KrellError):
    """Base exception for TTS-related failures."""

    pass


class TTSModelNotFoundError(TTSError):
    """TTS model files are missing."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        super().__init__(f"TTS model not found at {model_path}")


class TTSVoiceNotFoundError(TTSError):
    """Requested voice is not available."""

    def __init__(self, voice: str, available_voices: list[str] | None = None):
        self.voice = voice
        self.available_voices = available_voices
        message = f"Voice '{voice}' not found"
        if available_voices:
            message += f". Available: {', '.join(available_voices[:5])}"
        super().__init__(message)


class TTSDeviceError(TTSError):
    """GPU/device issues during TTS initialization or inference."""

    def __init__(self, device: str, cause: Exception | None = None):
        self.device = device
        self.cause = cause
        message = f"TTS device error on {device}"
        if cause:
            message += f": {cause}"
        super().__init__(message)


class TTSSynthesisError(TTSError):
    """Error during audio synthesis."""

    def __init__(self, text: str | None = None, cause: Exception | None = None):
        self.text = text
        self.cause = cause
        message = "TTS synthesis failed"
        if cause:
            message += f": {cause}"
        super().__init__(message)


# =============================================================================
# Plugin Errors
# =============================================================================


class PluginError(KrellError):
    """Base exception for plugin-related failures."""

    pass


class PluginLoadError(PluginError):
    """Failed to load a plugin."""

    def __init__(self, plugin_name: str, cause: Exception | None = None):
        self.plugin_name = plugin_name
        self.cause = cause
        message = f"Failed to load plugin '{plugin_name}'"
        if cause:
            message += f": {cause}"
        super().__init__(message)


class PluginConfigError(PluginError):
    """Invalid plugin configuration."""

    def __init__(self, plugin_name: str, config_key: str | None = None, message: str | None = None):
        self.plugin_name = plugin_name
        self.config_key = config_key
        msg = f"Invalid configuration for plugin '{plugin_name}'"
        if config_key:
            msg += f" (key: {config_key})"
        if message:
            msg += f": {message}"
        super().__init__(msg)


class PluginExecutionError(PluginError):
    """Error during plugin/tool execution."""

    def __init__(self, plugin_name: str, tool_name: str | None = None, cause: Exception | None = None):
        self.plugin_name = plugin_name
        self.tool_name = tool_name
        self.cause = cause
        message = f"Plugin '{plugin_name}' execution failed"
        if tool_name:
            message += f" (tool: {tool_name})"
        if cause:
            message += f": {cause}"
        super().__init__(message)


# =============================================================================
# WebSocket / Connection Errors
# =============================================================================


class WebSocketError(KrellError):
    """Base exception for WebSocket/connection errors."""

    pass


class ConnectionClosedError(WebSocketError):
    """Client disconnected gracefully."""

    def __init__(self, reason: str | None = None):
        self.reason = reason
        message = "WebSocket connection closed"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class MessageTooLargeError(WebSocketError):
    """Message exceeds size limit."""

    def __init__(self, size: int, max_size: int):
        self.size = size
        self.max_size = max_size
        super().__init__(f"Message size {size} exceeds limit {max_size}")


class ConnectionTimeoutError(WebSocketError):
    """Connection timed out."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        super().__init__(f"Connection timed out after {timeout}s")


# =============================================================================
# Service Discovery Errors
# =============================================================================


class ServiceError(KrellError):
    """Base exception for service-related errors."""

    pass


class ServiceAtCapacityError(ServiceError):
    """Service is operating at capacity but no serious error. Retry later."""

    def __init__(self, service: str):
        self.service = service
        super().__init__(f"{service} is at capacity, try again later")


class ServiceTimeoutError(ServiceError):
    """Service timed out."""

    def __init__(self, service: str, timeout: float | None = None):
        self.service = service
        self.timeout = timeout
        message = f"{service} timed out"
        if timeout:
            message += f" after {timeout}s"
        super().__init__(message)


class ServiceUnavailableError(ServiceError):
    """Service is unavailable."""

    def __init__(self, service: str, cause: Exception | None = None):
        self.service = service
        self.cause = cause
        message = f"{service} is unavailable"
        if cause:
            message += f": {cause}"
        super().__init__(message)


# =============================================================================
# Database Errors
# =============================================================================


class DatabaseError(KrellError):
    """Base exception for database-related errors."""

    pass


class DatabaseConnectionError(DatabaseError):
    """Cannot connect to database."""

    def __init__(self, db_path: str, cause: Exception | None = None):
        self.db_path = db_path
        self.cause = cause
        message = f"Cannot connect to database at {db_path}"
        if cause:
            message += f": {cause}"
        super().__init__(message)


class DatabaseMigrationError(DatabaseError):
    """Database migration failed."""

    def __init__(self, migration: str | None = None, cause: Exception | None = None):
        self.migration = migration
        self.cause = cause
        message = "Database migration failed"
        if migration:
            message += f" ({migration})"
        if cause:
            message += f": {cause}"
        super().__init__(message)


# =============================================================================
# Cache Errors
# =============================================================================


class CacheError(KrellError):
    """Base exception for cache-related errors."""

    pass


class CacheConnectionError(CacheError):
    """Cannot connect to cache backend."""

    def __init__(self, backend: str, cause: Exception | None = None):
        self.backend = backend
        self.cause = cause
        message = f"Cannot connect to {backend} cache"
        if cause:
            message += f": {cause}"
        super().__init__(message)


# =============================================================================
# Validation Errors
# =============================================================================


class ValidationError(KrellError):
    """Input validation failed."""

    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.value = value
        super().__init__(f"Validation failed for '{field}': {message}")
