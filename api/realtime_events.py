"""
OpenAI Realtime API Event Schemas

Based on: https://platform.openai.com/docs/api-reference/realtime
Simplified for Krell's use case - continuous voice conversation with LLM.

Event flow:
- Client → Server: InputAudioBufferAppend, SessionUpdate, ResponseCancel
- Server → Client: ResponseAudioDelta, ResponseTextDelta, TranscriptionDelta, Error
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, Union
from enum import Enum


# ============================================================================
# Client → Server Events (Received from browser)
# ============================================================================


class InputAudioBufferAppend(BaseModel):
    """
    Client sends audio chunk to append to input buffer.

    Audio must be base64-encoded Opus or PCM16.
    """

    type: Literal["input_audio_buffer.append"] = "input_audio_buffer.append"
    audio: str  # base64-encoded audio


class SessionConfig(BaseModel):
    """Session configuration"""

    voice: Optional[str] = None
    instructions: Optional[str] = None  # System prompt
    input_audio_format: Optional[Literal["pcm16", "opus"]] = "opus"
    output_audio_format: Optional[Literal["pcm16", "opus"]] = "opus"
    turn_detection: Optional[dict] = None  # VAD configuration


class SessionUpdate(BaseModel):
    """Client requests session configuration update"""

    type: Literal["session.update"] = "session.update"
    session: SessionConfig


class ResponseCancel(BaseModel):
    """Client requests to cancel ongoing response generation"""

    type: Literal["response.cancel"] = "response.cancel"


# Union type for all client events
ClientEvent = Union[InputAudioBufferAppend, SessionUpdate, ResponseCancel]


# ============================================================================
# Server → Client Events (Sent to browser)
# ============================================================================


class SessionCreated(BaseModel):
    """Server confirms session creation"""

    type: Literal["session.created"] = "session.created"
    session: SessionConfig


class SessionUpdated(BaseModel):
    """Server confirms session update"""

    type: Literal["session.updated"] = "session.updated"
    session: SessionConfig


class InputAudioBufferCommitted(BaseModel):
    """
    Server committed audio buffer (user stopped speaking).
    Transcription will follow.
    """

    type: Literal["input_audio_buffer.committed"] = "input_audio_buffer.committed"


class InputAudioBufferCleared(BaseModel):
    """Server cleared the audio buffer"""

    type: Literal["input_audio_buffer.cleared"] = "input_audio_buffer.cleared"


class ConversationItemCreated(BaseModel):
    """A new item was added to conversation (user message, assistant response, etc.)"""

    type: Literal["conversation.item.created"] = "conversation.item.created"
    item: dict  # Full item object


class ResponseCreated(BaseModel):
    """Server started generating a response"""

    type: Literal["response.created"] = "response.created"
    response: dict


class ResponseDone(BaseModel):
    """Server finished generating response"""

    type: Literal["response.done"] = "response.done"
    response: dict


class ResponseTextDelta(BaseModel):
    """
    Streaming text chunk from LLM.

    These arrive as the LLM generates text, before TTS.
    """

    type: Literal["response.text.delta"] = "response.text.delta"
    delta: str  # Text chunk
    item_id: Optional[str] = None


class ResponseTextDone(BaseModel):
    """Text generation complete"""

    type: Literal["response.text.done"] = "response.text.done"
    text: str  # Complete text


class ResponseAudioDelta(BaseModel):
    """
    Streaming audio chunk (TTS output).

    Audio is base64-encoded Opus or PCM16.
    """

    type: Literal["response.audio.delta"] = "response.audio.delta"
    delta: str  # base64-encoded audio chunk
    item_id: Optional[str] = None


class ResponseAudioDone(BaseModel):
    """Audio generation complete"""

    type: Literal["response.audio.done"] = "response.audio.done"


class ResponseAudioTranscriptDelta(BaseModel):
    """
    Transcript of what the TTS is saying.

    Useful for showing subtitles while audio plays.
    """

    type: Literal["response.audio_transcript.delta"] = "response.audio_transcript.delta"
    delta: str
    item_id: Optional[str] = None


class ResponseAudioTranscriptDone(BaseModel):
    """Audio transcript complete"""

    type: Literal["response.audio_transcript.done"] = "response.audio_transcript.done"
    transcript: str


class InputAudioTranscriptionCompleted(BaseModel):
    """
    User's speech was transcribed.

    This is what the user said (STT output).
    """

    type: Literal["conversation.item.input_audio_transcription.completed"] = (
        "conversation.item.input_audio_transcription.completed"
    )
    item_id: str
    transcript: str


class InputAudioTranscriptionDelta(BaseModel):
    """
    Streaming transcription of user's speech.

    Allows showing real-time STT feedback.
    """

    type: Literal["conversation.item.input_audio_transcription.delta"] = (
        "conversation.item.input_audio_transcription.delta"
    )
    item_id: str
    delta: str


class ErrorType(str, Enum):
    """Error types"""

    INVALID_REQUEST = "invalid_request_error"
    AUTHENTICATION = "authentication_error"
    SERVER_ERROR = "server_error"
    RATE_LIMIT = "rate_limit_error"


class ErrorDetails(BaseModel):
    """Error details"""

    type: ErrorType
    message: str
    code: Optional[str] = None
    param: Optional[str] = None


class Error(BaseModel):
    """Server error event"""

    type: Literal["error"] = "error"
    error: ErrorDetails


# Union type for all server events
ServerEvent = Union[
    SessionCreated,
    SessionUpdated,
    InputAudioBufferCommitted,
    InputAudioBufferCleared,
    ConversationItemCreated,
    ResponseCreated,
    ResponseDone,
    ResponseTextDelta,
    ResponseTextDone,
    ResponseAudioDelta,
    ResponseAudioDone,
    ResponseAudioTranscriptDelta,
    ResponseAudioTranscriptDone,
    InputAudioTranscriptionCompleted,
    InputAudioTranscriptionDelta,
    Error,
]


# ============================================================================
# Krell-Specific Extensions
# ============================================================================


class KrellDebugInfo(BaseModel):
    """
    Debug information event (not part of OpenAI API).

    Useful for showing system state in UI.
    """

    type: Literal["krell.debug"] = "krell.debug"
    state: str  # Current state: listening, processing, speaking
    buffers: Optional[dict] = None  # Buffer sizes, queue lengths, etc.
    latency: Optional[dict] = None  # Latency measurements


class KrellInterruption(BaseModel):
    """
    User interrupted the AI (not part of OpenAI API).

    Sent when user starts speaking while AI is talking.
    """

    type: Literal["krell.interruption"] = "krell.interruption"
    message: str = "User interrupted"


# Extend server events with Krell-specific ones
ServerEventExtended = Union[ServerEvent, KrellDebugInfo, KrellInterruption]


# ============================================================================
# Helper Functions
# ============================================================================


def make_error(
    error_type: ErrorType,
    message: str,
    code: Optional[str] = None,
    param: Optional[str] = None,
) -> Error:
    """Create an error event"""
    return Error(
        error=ErrorDetails(type=error_type, message=message, code=code, param=param)
    )


def make_text_delta(text: str, item_id: Optional[str] = None) -> ResponseTextDelta:
    """Create a text delta event"""
    return ResponseTextDelta(delta=text, item_id=item_id)


def make_audio_delta(
    audio_base64: str, item_id: Optional[str] = None
) -> ResponseAudioDelta:
    """Create an audio delta event"""
    return ResponseAudioDelta(delta=audio_base64, item_id=item_id)


def make_transcription_delta(text: str, item_id: str) -> InputAudioTranscriptionDelta:
    """Create a transcription delta event (user's speech being recognized)"""
    return InputAudioTranscriptionDelta(item_id=item_id, delta=text)


def make_transcription_completed(
    text: str, item_id: str
) -> InputAudioTranscriptionCompleted:
    """Create a transcription completed event"""
    return InputAudioTranscriptionCompleted(item_id=item_id, transcript=text)
