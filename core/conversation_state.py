"""
Conversation State Machine - Explicit state management for conversation flow.

This module provides a state machine for managing conversation state with:
- Clear state definitions
- Valid transition rules
- State change events
- Interruption handling

States:
    idle         - Waiting for user input
    user_typing  - User is typing (for typing indicators)
    user_speaking - User audio input detected
    processing   - LLM is generating response
    bot_speaking - TTS audio is playing
    tool_executing - Tool is running
    error        - Error state

Usage:
    from core.conversation_state import ConversationStateMachine, State

    state_machine = ConversationStateMachine(
        on_state_change=lambda old, new: print(f"{old} -> {new}")
    )

    # User starts speaking
    state_machine.user_started_speaking()
    assert state_machine.state == State.USER_SPEAKING

    # User stops, we start processing
    state_machine.user_stopped_speaking()
    state_machine.start_processing()

    # Handle interruption
    state_machine.interrupt()  # Goes back to idle
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class State(str, Enum):
    """Conversation states."""

    IDLE = "idle"
    USER_TYPING = "user_typing"
    USER_SPEAKING = "user_speaking"
    PROCESSING = "processing"
    BOT_SPEAKING = "bot_speaking"
    TOOL_EXECUTING = "tool_executing"
    ERROR = "error"


@dataclass
class StateTransition:
    """Record of a state transition."""

    from_state: State
    to_state: State
    timestamp: datetime = field(default_factory=datetime.now)
    reason: Optional[str] = None


# Valid state transitions
VALID_TRANSITIONS: Dict[State, Set[State]] = {
    State.IDLE: {
        State.USER_TYPING,
        State.USER_SPEAKING,
        State.PROCESSING,  # Direct text input
        State.ERROR,
    },
    State.USER_TYPING: {
        State.IDLE,  # Typing cancelled
        State.PROCESSING,  # Text submitted
        State.USER_SPEAKING,  # Switched to voice
        State.ERROR,
    },
    State.USER_SPEAKING: {
        State.IDLE,  # Speech cancelled
        State.PROCESSING,  # Speech complete
        State.ERROR,
    },
    State.PROCESSING: {
        State.BOT_SPEAKING,  # Response ready
        State.TOOL_EXECUTING,  # Tool call needed
        State.IDLE,  # Processing complete (no audio)
        State.USER_SPEAKING,  # Interrupted by user
        State.ERROR,
    },
    State.BOT_SPEAKING: {
        State.IDLE,  # Response complete
        State.USER_SPEAKING,  # Interrupted by user
        State.PROCESSING,  # More to generate
        State.TOOL_EXECUTING,  # Tool call mid-response
        State.ERROR,
    },
    State.TOOL_EXECUTING: {
        State.PROCESSING,  # Tool complete, continue
        State.BOT_SPEAKING,  # Tool complete, speak result
        State.IDLE,  # Tool complete, done
        State.ERROR,
    },
    State.ERROR: {
        State.IDLE,  # Error acknowledged
    },
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: State, to_state: State):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition from {from_state.value} to {to_state.value}"
        )


class ConversationStateMachine:
    """
    State machine for managing conversation flow.

    Ensures valid state transitions and emits events on state changes.

    Attributes:
        state: Current conversation state
        history: List of state transitions
    """

    def __init__(
        self,
        initial_state: State = State.IDLE,
        on_state_change: Optional[Callable[[State, State], None]] = None,
        strict: bool = True,
    ):
        """
        Initialize the state machine.

        Args:
            initial_state: Starting state
            on_state_change: Callback for state changes (old_state, new_state)
            strict: If True, raise on invalid transitions; if False, log warning
        """
        self._state = initial_state
        self._on_state_change = on_state_change
        self._strict = strict
        self._history: List[StateTransition] = []
        self._state_entered_at = datetime.now()

    @property
    def state(self) -> State:
        """Current state."""
        return self._state

    @property
    def history(self) -> List[StateTransition]:
        """History of state transitions."""
        return self._history.copy()

    @property
    def state_duration(self) -> float:
        """Seconds since entering current state."""
        return (datetime.now() - self._state_entered_at).total_seconds()

    def can_transition_to(self, new_state: State) -> bool:
        """Check if a transition to the given state is valid."""
        return new_state in VALID_TRANSITIONS.get(self._state, set())

    def _transition_to(self, new_state: State, reason: Optional[str] = None) -> bool:
        """
        Attempt to transition to a new state.

        Args:
            new_state: Target state
            reason: Optional reason for the transition

        Returns:
            True if transition succeeded

        Raises:
            InvalidTransitionError: If strict mode and transition invalid
        """
        if new_state == self._state:
            return True  # Already in this state

        if not self.can_transition_to(new_state):
            if self._strict:
                raise InvalidTransitionError(self._state, new_state)
            else:
                logger.warning(
                    f"Invalid state transition: {self._state.value} -> {new_state.value}"
                )
                return False

        old_state = self._state
        self._state = new_state
        self._state_entered_at = datetime.now()

        # Record transition
        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            reason=reason,
        )
        self._history.append(transition)

        logger.debug(f"State: {old_state.value} -> {new_state.value} ({reason or 'no reason'})")

        # Emit callback
        if self._on_state_change:
            try:
                self._on_state_change(old_state, new_state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")

        return True

    # -------------------------------------------------------------------------
    # High-level state transition methods
    # -------------------------------------------------------------------------

    def user_started_typing(self) -> bool:
        """User started typing text input."""
        return self._transition_to(State.USER_TYPING, "user typing")

    def user_stopped_typing(self) -> bool:
        """User cancelled typing without submitting."""
        return self._transition_to(State.IDLE, "typing cancelled")

    def user_submitted_text(self) -> bool:
        """User submitted text input."""
        return self._transition_to(State.PROCESSING, "text submitted")

    def user_started_speaking(self) -> bool:
        """User started speaking (voice input detected)."""
        return self._transition_to(State.USER_SPEAKING, "speech started")

    def user_stopped_speaking(self) -> bool:
        """User stopped speaking."""
        # This usually means we're about to process
        # The caller should follow up with start_processing()
        return True  # Stay in USER_SPEAKING until processing starts

    def start_processing(self) -> bool:
        """Start processing user input."""
        return self._transition_to(State.PROCESSING, "processing started")

    def start_speaking(self) -> bool:
        """Bot started speaking (TTS output)."""
        return self._transition_to(State.BOT_SPEAKING, "bot speaking")

    def stop_speaking(self) -> bool:
        """Bot finished speaking."""
        return self._transition_to(State.IDLE, "bot finished speaking")

    def start_tool_execution(self, tool_name: Optional[str] = None) -> bool:
        """Tool execution started."""
        reason = f"executing tool: {tool_name}" if tool_name else "tool execution"
        return self._transition_to(State.TOOL_EXECUTING, reason)

    def tool_execution_complete(self) -> bool:
        """Tool execution finished."""
        # Usually goes back to processing to continue response
        return self._transition_to(State.PROCESSING, "tool complete")

    def interrupt(self, reason: str = "interrupted") -> bool:
        """
        Interrupt current activity (e.g., user started speaking while bot is speaking).

        This is a special transition that can happen from multiple states.
        """
        if self._state == State.IDLE:
            return True  # Already idle

        # Interruption is always valid from bot_speaking or processing
        if self._state in {State.BOT_SPEAKING, State.PROCESSING}:
            return self._transition_to(State.USER_SPEAKING, reason)

        return self._transition_to(State.IDLE, reason)

    def error(self, error_message: Optional[str] = None) -> bool:
        """Transition to error state."""
        reason = f"error: {error_message}" if error_message else "error"
        return self._transition_to(State.ERROR, reason)

    def recover_from_error(self) -> bool:
        """Recover from error state to idle."""
        return self._transition_to(State.IDLE, "recovered from error")

    def reset(self) -> None:
        """Reset to idle state (unconditionally)."""
        if self._state != State.IDLE:
            self._history.append(
                StateTransition(
                    from_state=self._state,
                    to_state=State.IDLE,
                    reason="reset",
                )
            )
        self._state = State.IDLE
        self._state_entered_at = datetime.now()

    # -------------------------------------------------------------------------
    # State queries
    # -------------------------------------------------------------------------

    def is_idle(self) -> bool:
        """Check if in idle state."""
        return self._state == State.IDLE

    def is_user_active(self) -> bool:
        """Check if user is actively providing input."""
        return self._state in {State.USER_TYPING, State.USER_SPEAKING}

    def is_bot_active(self) -> bool:
        """Check if bot is generating or speaking."""
        return self._state in {State.PROCESSING, State.BOT_SPEAKING, State.TOOL_EXECUTING}

    def can_be_interrupted(self) -> bool:
        """Check if current state can be interrupted by user."""
        return self._state in {State.PROCESSING, State.BOT_SPEAKING}

    def to_dict(self) -> Dict:
        """Get state machine status as a dictionary."""
        return {
            "state": self._state.value,
            "state_duration_seconds": self.state_duration,
            "can_be_interrupted": self.can_be_interrupted(),
            "is_user_active": self.is_user_active(),
            "is_bot_active": self.is_bot_active(),
            "transition_count": len(self._history),
        }


class ConversationStateManager:
    """
    Manages state machines for multiple conversations.

    Usage:
        manager = ConversationStateManager()
        state = manager.get_or_create("conversation_123")
        state.user_started_speaking()
    """

    def __init__(self, on_state_change: Optional[Callable[[str, State, State], None]] = None):
        """
        Initialize the manager.

        Args:
            on_state_change: Callback with (conversation_id, old_state, new_state)
        """
        self._machines: Dict[str, ConversationStateMachine] = {}
        self._on_state_change = on_state_change

    def get_or_create(self, conversation_id: str) -> ConversationStateMachine:
        """Get or create a state machine for a conversation."""
        if conversation_id not in self._machines:
            # Create callback that includes conversation_id
            def callback(old: State, new: State) -> None:
                if self._on_state_change:
                    self._on_state_change(conversation_id, old, new)

            self._machines[conversation_id] = ConversationStateMachine(
                on_state_change=callback
            )

        return self._machines[conversation_id]

    def get(self, conversation_id: str) -> Optional[ConversationStateMachine]:
        """Get a state machine if it exists."""
        return self._machines.get(conversation_id)

    def remove(self, conversation_id: str) -> None:
        """Remove a conversation's state machine."""
        self._machines.pop(conversation_id, None)

    def get_all_states(self) -> Dict[str, State]:
        """Get current states for all conversations."""
        return {cid: sm.state for cid, sm in self._machines.items()}

    def get_active_conversations(self) -> List[str]:
        """Get IDs of conversations with active processing."""
        return [
            cid for cid, sm in self._machines.items()
            if sm.is_bot_active() or sm.is_user_active()
        ]

    def interrupt_all(self, reason: str = "global interrupt") -> None:
        """Interrupt all active conversations."""
        for sm in self._machines.values():
            if sm.can_be_interrupted():
                sm.interrupt(reason)
