"""
OpenAI Realtime API-Compatible Event System.

This module defines typed Pydantic models for WebSocket events that are
compatible with the OpenAI Realtime API format, with Krell extensions.

The event system provides:
- Type-safe event handling with Pydantic validation
- Discriminated unions for automatic event parsing
- Self-documenting API through schema generation
- Compatibility with OpenAI Realtime API clients

Usage:
    from api.events import ServerEvent, ClientEvent, parse_server_event

    # Parse incoming client event
    event = ClientEvent.model_validate_json(json_data)

    # Create server event
    event = ResponseTextDelta(delta="Hello")
    json_data = event.model_dump_json()

    # Parse with discriminated union
    event = parse_server_event(data)
    match event:
        case ResponseTextDelta(delta=text):
            print(f"Text: {text}")
        case ResponseAudioDelta(delta=audio):
            play_audio(audio)
"""

import random
import string
from typing import Any, Dict, List, Literal, Optional, Union, get_args, get_origin

from pydantic import BaseModel, Field, model_validator


def _random_id(prefix: str = "event") -> str:
    """Generate a random event ID like 'event_Xk9mL2pQ3nR'."""
    chars = string.ascii_letters + string.digits
    suffix = "".join(random.choices(chars, k=12))
    return f"{prefix}_{suffix}"


# =============================================================================
# Base Event Class
# =============================================================================


class BaseEvent(BaseModel):
    """
    Base class for all events.

    The 'type' field is automatically set from the Literal type annotation
    of subclasses. Each event has a unique event_id for tracking.
    """

    type: str = ""
    event_id: str = Field(default_factory=_random_id)

    @model_validator(mode="after")
    def _set_type_from_annotation(self) -> "BaseEvent":
        """Automatically set type from the Literal annotation."""
        if type(self) == BaseEvent:
            raise ValueError("Cannot instantiate BaseEvent directly")

        # Get the type annotation from the subclass
        type_field = self.__class__.model_fields.get("type")
        if type_field and type_field.annotation:
            annotation = type_field.annotation
            if get_origin(annotation) is Literal:
                args = get_args(annotation)
                if args:
                    self.type = args[0]

        return self

    class Config:
        extra = "allow"  # Allow additional fields for extensions


# =============================================================================
# Error Events
# =============================================================================


class ErrorDetails(BaseModel):
    """Details about an error."""

    type: str = Field(description="Error type identifier")
    code: Optional[str] = Field(default=None, description="Error code")
    message: str = Field(description="Human-readable error message")
    param: Optional[str] = Field(default=None, description="Parameter that caused the error")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional error details")


class Error(BaseEvent):
    """Error event sent when something goes wrong."""

    type: Literal["error"] = "error"
    error: ErrorDetails


# =============================================================================
# Session Events
# =============================================================================


class SessionConfig(BaseModel):
    """Session configuration."""

    voice: Optional[str] = Field(default=None, description="Voice for TTS")
    language: Optional[str] = Field(default="en-us", description="Language code")
    allow_recording: bool = Field(default=False, description="Whether to record the session")
    context_limit: Optional[int] = Field(default=None, description="Max messages in context")


class SessionUpdate(BaseEvent):
    """Client request to update session configuration."""

    type: Literal["session.update"] = "session.update"
    session: SessionConfig


class SessionUpdated(BaseEvent):
    """Server confirmation of session configuration update."""

    type: Literal["session.updated"] = "session.updated"
    session: SessionConfig


class SessionCreated(BaseEvent):
    """Server notification that a new session was created."""

    type: Literal["session.created"] = "session.created"
    session_id: str = Field(description="Unique session identifier")
    conversation_id: Optional[str] = Field(default=None, description="Associated conversation ID")


# =============================================================================
# Input Events (Client -> Server)
# =============================================================================


class InputTextAppend(BaseEvent):
    """Client sends text input."""

    type: Literal["input.text.append"] = "input.text.append"
    text: str = Field(description="Text to append to input")


class InputTextCommit(BaseEvent):
    """Client commits text input for processing."""

    type: Literal["input.text.commit"] = "input.text.commit"
    text: str = Field(default="", description="Text content to process")
    conversation_id: Optional[str] = Field(default=None, description="Conversation to continue")


class InputAudioBufferAppend(BaseEvent):
    """Client sends audio data."""

    type: Literal["input_audio_buffer.append"] = "input_audio_buffer.append"
    audio: str = Field(description="Base64-encoded audio data")


class InputAudioBufferCommit(BaseEvent):
    """Client commits audio buffer for processing."""

    type: Literal["input_audio_buffer.commit"] = "input_audio_buffer.commit"


class InputAudioBufferClear(BaseEvent):
    """Client clears the audio buffer."""

    type: Literal["input_audio_buffer.clear"] = "input_audio_buffer.clear"


# =============================================================================
# Speech Detection Events
# =============================================================================


class InputAudioBufferSpeechStarted(BaseEvent):
    """Speech detected in audio input."""

    type: Literal["input_audio_buffer.speech_started"] = "input_audio_buffer.speech_started"
    audio_start_ms: Optional[int] = Field(default=None, description="Start time in milliseconds")


class InputAudioBufferSpeechStopped(BaseEvent):
    """Speech ended in audio input."""

    type: Literal["input_audio_buffer.speech_stopped"] = "input_audio_buffer.speech_stopped"
    audio_end_ms: Optional[int] = Field(default=None, description="End time in milliseconds")


# =============================================================================
# Response Events (Server -> Client)
# =============================================================================


class ResponseCreated(BaseEvent):
    """Server started generating a response."""

    type: Literal["response.created"] = "response.created"
    response_id: str = Field(default_factory=lambda: _random_id("resp"))
    conversation_id: Optional[str] = Field(default=None)
    status: Literal["in_progress", "completed", "cancelled", "failed"] = "in_progress"


class ResponseTextDelta(BaseEvent):
    """Streaming text chunk from the response."""

    type: Literal["response.text.delta"] = "response.text.delta"
    delta: str = Field(description="Text chunk")
    response_id: Optional[str] = Field(default=None)


class ResponseTextDone(BaseEvent):
    """Text generation complete."""

    type: Literal["response.text.done"] = "response.text.done"
    text: str = Field(description="Complete response text")
    response_id: Optional[str] = Field(default=None)


class ResponseAudioDelta(BaseEvent):
    """Streaming audio chunk from the response."""

    type: Literal["response.audio.delta"] = "response.audio.delta"
    delta: str = Field(description="Base64-encoded audio data")
    response_id: Optional[str] = Field(default=None)


class ResponseAudioDone(BaseEvent):
    """Audio generation complete."""

    type: Literal["response.audio.done"] = "response.audio.done"
    response_id: Optional[str] = Field(default=None)


class ResponseDone(BaseEvent):
    """Response generation complete."""

    type: Literal["response.done"] = "response.done"
    response_id: Optional[str] = Field(default=None)
    conversation_id: Optional[str] = Field(default=None)
    status: Literal["completed", "cancelled", "failed"] = "completed"
    usage: Optional[Dict[str, int]] = Field(default=None, description="Token usage stats")


# =============================================================================
# Tool Events
# =============================================================================


class ToolCallCreated(BaseEvent):
    """Server is invoking a tool."""

    type: Literal["tool_call.created"] = "tool_call.created"
    tool_call_id: str = Field(default_factory=lambda: _random_id("call"))
    name: str = Field(description="Tool name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolCallDelta(BaseEvent):
    """Streaming tool call arguments."""

    type: Literal["tool_call.delta"] = "tool_call.delta"
    tool_call_id: str
    delta: str = Field(description="Argument JSON chunk")


class ToolCallDone(BaseEvent):
    """Tool call arguments complete."""

    type: Literal["tool_call.done"] = "tool_call.done"
    tool_call_id: str
    name: str
    arguments: Dict[str, Any]


class ToolResult(BaseEvent):
    """Tool execution result."""

    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    result: Any = Field(description="Tool result (JSON-serializable)")
    error: Optional[str] = Field(default=None, description="Error message if failed")


# =============================================================================
# Conversation Events
# =============================================================================


class ConversationCreated(BaseEvent):
    """New conversation created."""

    type: Literal["conversation.created"] = "conversation.created"
    conversation_id: str


class ConversationItemCreated(BaseEvent):
    """New item added to conversation."""

    type: Literal["conversation.item.created"] = "conversation.item.created"
    conversation_id: str
    item_id: str
    role: Literal["user", "assistant", "system"]
    content: Optional[str] = None


class ConversationItemInputAudioTranscriptionDelta(BaseEvent):
    """Streaming transcription of input audio."""

    type: Literal["conversation.item.input_audio_transcription.delta"] = (
        "conversation.item.input_audio_transcription.delta"
    )
    delta: str = Field(description="Transcription text chunk")
    start_time: Optional[float] = Field(default=None, description="Start time in seconds")


class ConversationItemInputAudioTranscriptionDone(BaseEvent):
    """Input audio transcription complete."""

    type: Literal["conversation.item.input_audio_transcription.done"] = (
        "conversation.item.input_audio_transcription.done"
    )
    transcript: str = Field(description="Complete transcription")


# =============================================================================
# Krell Extension Events
# =============================================================================


class KrellStateUpdate(BaseEvent):
    """Krell-specific state update."""

    type: Literal["krell.state.update"] = "krell.state.update"
    state: str = Field(description="Current conversation state")
    previous_state: Optional[str] = Field(default=None)


class KrellMetrics(BaseEvent):
    """Krell-specific metrics event."""

    type: Literal["krell.metrics"] = "krell.metrics"
    latency_ms: Optional[int] = Field(default=None, description="Response latency")
    tokens_used: Optional[int] = Field(default=None)
    audio_duration_ms: Optional[int] = Field(default=None)


class KrellInterrupted(BaseEvent):
    """Response was interrupted by user."""

    type: Literal["krell.interrupted"] = "krell.interrupted"
    reason: Literal["user_speech", "cancel_request", "timeout"] = "user_speech"


# =============================================================================
# Discriminated Unions
# =============================================================================

# Server -> Client events
ServerEvent = Union[
    Error,
    SessionUpdated,
    SessionCreated,
    InputAudioBufferSpeechStarted,
    InputAudioBufferSpeechStopped,
    ResponseCreated,
    ResponseTextDelta,
    ResponseTextDone,
    ResponseAudioDelta,
    ResponseAudioDone,
    ResponseDone,
    ToolCallCreated,
    ToolCallDelta,
    ToolCallDone,
    ToolResult,
    ConversationCreated,
    ConversationItemCreated,
    ConversationItemInputAudioTranscriptionDelta,
    ConversationItemInputAudioTranscriptionDone,
    KrellStateUpdate,
    KrellMetrics,
    KrellInterrupted,
]

# Client -> Server events
ClientEvent = Union[
    SessionUpdate,
    InputTextAppend,
    InputTextCommit,
    InputAudioBufferAppend,
    InputAudioBufferCommit,
    InputAudioBufferClear,
]

# All events
Event = Union[ServerEvent, ClientEvent]


# =============================================================================
# Parsing Helpers
# =============================================================================

# Map of event type strings to their classes
_SERVER_EVENT_MAP: Dict[str, type[BaseEvent]] = {
    "error": Error,
    "session.updated": SessionUpdated,
    "session.created": SessionCreated,
    "input_audio_buffer.speech_started": InputAudioBufferSpeechStarted,
    "input_audio_buffer.speech_stopped": InputAudioBufferSpeechStopped,
    "response.created": ResponseCreated,
    "response.text.delta": ResponseTextDelta,
    "response.text.done": ResponseTextDone,
    "response.audio.delta": ResponseAudioDelta,
    "response.audio.done": ResponseAudioDone,
    "response.done": ResponseDone,
    "tool_call.created": ToolCallCreated,
    "tool_call.delta": ToolCallDelta,
    "tool_call.done": ToolCallDone,
    "tool_result": ToolResult,
    "conversation.created": ConversationCreated,
    "conversation.item.created": ConversationItemCreated,
    "conversation.item.input_audio_transcription.delta": ConversationItemInputAudioTranscriptionDelta,
    "conversation.item.input_audio_transcription.done": ConversationItemInputAudioTranscriptionDone,
    "krell.state.update": KrellStateUpdate,
    "krell.metrics": KrellMetrics,
    "krell.interrupted": KrellInterrupted,
}

_CLIENT_EVENT_MAP: Dict[str, type[BaseEvent]] = {
    "session.update": SessionUpdate,
    "input.text.append": InputTextAppend,
    "input.text.commit": InputTextCommit,
    "input_audio_buffer.append": InputAudioBufferAppend,
    "input_audio_buffer.commit": InputAudioBufferCommit,
    "input_audio_buffer.clear": InputAudioBufferClear,
}


def parse_event(data: Dict[str, Any]) -> Event:
    """
    Parse a raw event dict into a typed event object.

    Args:
        data: Raw event dictionary with 'type' field

    Returns:
        Typed event object

    Raises:
        ValueError: If event type is unknown
    """
    event_type = data.get("type")
    if not event_type:
        raise ValueError("Event missing 'type' field")

    # Try server events first
    if event_type in _SERVER_EVENT_MAP:
        return _SERVER_EVENT_MAP[event_type].model_validate(data)

    # Then client events
    if event_type in _CLIENT_EVENT_MAP:
        return _CLIENT_EVENT_MAP[event_type].model_validate(data)

    raise ValueError(f"Unknown event type: {event_type}")


def parse_server_event(data: Dict[str, Any]) -> ServerEvent:
    """Parse a server event."""
    event = parse_event(data)
    if not isinstance(event, tuple(get_args(ServerEvent))):
        raise ValueError(f"Not a server event: {data.get('type')}")
    return event  # type: ignore


def parse_client_event(data: Dict[str, Any]) -> ClientEvent:
    """Parse a client event."""
    event = parse_event(data)
    if not isinstance(event, tuple(get_args(ClientEvent))):
        raise ValueError(f"Not a client event: {data.get('type')}")
    return event  # type: ignore


def make_error(error_type: str, message: str, code: Optional[str] = None) -> Error:
    """
    Create an error event.

    Args:
        error_type: Error type identifier
        message: Human-readable error message
        code: Optional error code

    Returns:
        Error event
    """
    return Error(error=ErrorDetails(type=error_type, message=message, code=code))
