"""
Krell Backend - API Schemas (Pydantic Models)
"""

from pydantic import BaseModel
from typing import Optional, List


class ConversationRequest(BaseModel):
    """Request model for storing conversations"""

    user_message: str
    ai_response: str


class ConversationResponse(BaseModel):
    """Response model for storing conversations"""

    success: bool
    conversation_id: Optional[int] = None
    embedding_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    version: str = "0.1.0"


class ConfigResponse(BaseModel):
    """Configuration response"""

    agentic_enabled: bool
    loaded_plugins: List[str] = []


class ChatRequest(BaseModel):
    """Request model for chat generation (new agentic API)"""

    conversation_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    """Response model for chat generation (new agentic API)"""

    response: str
    conversation_id: str
    tool_calls: List[dict] = []
    metadata: dict = {}


class TTSRequest(BaseModel):
    """Request model for TTS streaming (non-standard since we stream response)."""

    text: str
    voice: Optional[str] = None
    format: Optional[str] = None  # wav/mp3


class ChatWithTTSRequest(BaseModel):
    """Request model for combined chat + TTS streaming endpoint."""

    message: str
    conversation_id: Optional[str] = None
    use_context: Optional[bool] = True
    voice: Optional[str] = None
    format: Optional[str] = None  # wav/mp3


class SessionCreateRequest(BaseModel):
    """Request model for creating a new conversation session"""

    title: Optional[str] = None


class SessionResponse(BaseModel):
    """Response model for a conversation session"""

    id: int
    title: Optional[str]
    created_at: str
    updated_at: str
    message_count: Optional[int] = 0
    last_message_time: Optional[str] = None


class SessionListResponse(BaseModel):
    """Response model for list of conversation sessions"""

    sessions: List[SessionResponse]
    count: int


class MessageResponse(BaseModel):
    """Response model for a message"""

    id: int
    user_message: str
    ai_response: str
    timestamp: str
    embedding_id: Optional[str] = None


class SessionMessagesResponse(BaseModel):
    """Response model for session messages"""

    session_id: int
    messages: List[MessageResponse]


class AddMessageRequest(BaseModel):
    """Request model for adding a message to a session"""

    session_id: int
    user_message: str
    ai_response: str


class UpdateSessionTitleRequest(BaseModel):
    """Request model for updating session title"""

    title: str


class DeleteResponse(BaseModel):
    """Response model for delete operations"""

    success: bool
    message: Optional[str] = None


# New schemas for Task 7 (Agentic API)


class ConversationListResponse(BaseModel):
    """Response model for listing conversations"""

    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationDetailResponse(BaseModel):
    """Response model for conversation detail with messages"""

    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List["MessageDetailResponse"]


class MessageDetailResponse(BaseModel):
    """Response model for message details"""

    id: str
    role: str
    content: str
    timestamp: str
    tool_calls: Optional[List[dict]] = None


class UpdateConversationTitleRequest(BaseModel):
    """Request model for updating conversation title"""

    title: str


class JournalEntryResponse(BaseModel):
    """Response model for journal entry"""

    id: str
    content: str
    entry_type: str
    conversation_id: Optional[str]
    created_at: str


class SettingsResponse(BaseModel):
    """Response model for settings"""

    settings: dict


class SettingsUpdateRequest(BaseModel):
    """Request model for updating settings"""

    settings: dict
