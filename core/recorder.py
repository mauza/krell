"""
Event Recorder - JSONL-based event logging for debugging and replay.

This module provides a structured event recording system that:
- Records events to JSONL files for easy parsing
- Uses async file I/O to avoid blocking
- Supports privacy controls (exclude message content)
- Enables session replay for debugging

Usage:
    from core.recorder import Recorder, EventSender

    recorder = Recorder(recordings_dir=Path("./data/recordings"))

    # Record events during a session
    await recorder.add_event("client", {"type": "text", "content": "Hello"})
    await recorder.add_event("server", {"type": "response", "text": "Hi there!"})

    # Clean shutdown
    await recorder.shutdown(keep_recording=True)

JSONL format (one JSON object per line):
    {"timestamp": 1234567890.123, "sender": "client", "event": {...}}
    {"timestamp": 1234567890.456, "sender": "server", "event": {...}}
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import aiofiles
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Type alias for event sender
EventSender = Literal["client", "server"]


class RecordedEvent(BaseModel):
    """A recorded event with metadata."""

    timestamp_wall: float = Field(description="Wall clock timestamp (Unix epoch)")
    timestamp_iso: str = Field(description="ISO 8601 formatted timestamp")
    event_sender: EventSender = Field(description="Who sent the event (client/server)")
    session_id: str = Field(description="Session identifier")
    event_type: str = Field(description="Type of event")
    event: Dict[str, Any] = Field(description="The event data")

    class Config:
        extra = "allow"


class Recorder:
    """
    Records events between client and server to a JSONL file.

    Events are recorded with timestamps for replay and debugging.
    Audio data is anonymized by default (stores sample count, not raw audio).

    Attributes:
        path: Path to the recording file
        session_id: Unique identifier for this recording session
    """

    def __init__(
        self,
        recordings_dir: Path,
        session_id: Optional[str] = None,
        anonymize_audio: bool = True,
        exclude_content: bool = False,
    ):
        """
        Initialize a new recorder.

        Args:
            recordings_dir: Directory to store recordings
            session_id: Optional session ID (generated if not provided)
            anonymize_audio: If True, replace audio data with sample counts
            exclude_content: If True, exclude message content for privacy
        """
        self.session_id = session_id or _make_session_id()
        self.path = recordings_dir / f"{_make_filename()}.jsonl"
        self.anonymize_audio = anonymize_audio
        self.exclude_content = exclude_content
        self._opened_file: Optional[aiofiles.threadpool.binary.AsyncBufferedIOBase] = None
        self._event_count = 0

        # Ensure recordings directory exists
        recordings_dir.mkdir(parents=True, exist_ok=True)

    async def add_event(
        self,
        event_sender: EventSender,
        event: Dict[str, Any],
        event_type: Optional[str] = None,
    ) -> None:
        """
        Record an event to the file.

        If the recorder hasn't been opened yet, it will be opened automatically.
        Events are written immediately (no buffering beyond OS-level).

        Args:
            event_sender: Who sent the event ("client" or "server")
            event: The event data dictionary
            event_type: Optional event type (inferred from event if not provided)
        """
        # Open file on first event
        if self._opened_file is None:
            self._opened_file = await aiofiles.open(self.path, mode="a")
            logger.info(f"Started recording to {self.path}")

        # Infer event type if not provided
        if event_type is None:
            event_type = event.get("type", "unknown")

        # Process event for privacy
        processed_event = self._process_event(event)

        # Create recorded event
        now = datetime.now()
        recorded = RecordedEvent(
            timestamp_wall=now.timestamp(),
            timestamp_iso=now.isoformat(),
            event_sender=event_sender,
            session_id=self.session_id,
            event_type=event_type,
            event=processed_event,
        )

        # Write to file
        await self._opened_file.write(recorded.model_dump_json() + "\n")
        self._event_count += 1

    def _process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process event for privacy controls."""
        processed = event.copy()

        # Anonymize audio data
        if self.anonymize_audio:
            if "audio" in processed:
                # Replace audio data with metadata
                audio_data = processed["audio"]
                if isinstance(audio_data, (bytes, str)):
                    processed["audio"] = None
                    processed["audio_samples"] = len(audio_data) if isinstance(audio_data, bytes) else len(audio_data) // 4 * 3  # Rough base64 decode
            if "delta" in processed and processed.get("type", "").startswith("response.audio"):
                # Audio delta in realtime API format
                processed["delta"] = None
                processed["audio_length"] = len(event.get("delta", ""))

        # Exclude message content if requested
        if self.exclude_content:
            if "content" in processed:
                processed["content"] = "[REDACTED]"
            if "text" in processed:
                processed["text"] = "[REDACTED]"
            if "delta" in processed and processed.get("type", "").startswith("response.text"):
                processed["delta"] = "[REDACTED]"

        return processed

    async def flush(self) -> None:
        """Flush any buffered data to disk."""
        if self._opened_file is not None:
            await self._opened_file.flush()

    async def shutdown(self, keep_recording: bool = True) -> None:
        """
        Flush remaining events and close the recorder.

        Args:
            keep_recording: If False, delete the recording file.
                           Useful when user doesn't consent to recording.
        """
        if self._opened_file is not None:
            await self._opened_file.close()
            self._opened_file = None

            if keep_recording:
                logger.info(
                    f"Recording saved to {self.path} ({self._event_count} events)"
                )
            else:
                try:
                    self.path.unlink()
                    logger.info(f"Deleted recording {self.path} (consent not given)")
                except Exception as e:
                    logger.error(f"Failed to delete recording {self.path}: {e}")

    @property
    def event_count(self) -> int:
        """Number of events recorded."""
        return self._event_count

    @property
    def is_recording(self) -> bool:
        """Whether the recorder is actively recording."""
        return self._opened_file is not None


class RecordingReader:
    """
    Reads and parses recorded sessions.

    Usage:
        reader = RecordingReader(Path("./recordings/2024-01-15_abc123.jsonl"))
        async for event in reader.read_events():
            print(event.event_type, event.event)
    """

    def __init__(self, path: Path):
        """
        Initialize a recording reader.

        Args:
            path: Path to the JSONL recording file
        """
        self.path = path

    async def read_events(self):
        """
        Async generator that yields recorded events.

        Yields:
            RecordedEvent objects in chronological order
        """
        async with aiofiles.open(self.path, mode="r") as f:
            async for line in f:
                line = line.strip()
                if line:
                    try:
                        event = RecordedEvent.model_validate_json(line)
                        yield event
                    except Exception as e:
                        logger.warning(f"Failed to parse event: {e}")

    async def get_session_info(self) -> Dict[str, Any]:
        """
        Get summary information about the recording.

        Returns:
            Dict with session_id, event_count, duration, etc.
        """
        first_event: Optional[RecordedEvent] = None
        last_event: Optional[RecordedEvent] = None
        event_count = 0
        event_types: Dict[str, int] = {}

        async for event in self.read_events():
            if first_event is None:
                first_event = event
            last_event = event
            event_count += 1
            event_types[event.event_type] = event_types.get(event.event_type, 0) + 1

        if first_event is None or last_event is None:
            return {
                "session_id": None,
                "event_count": 0,
                "duration_seconds": 0,
                "event_types": {},
            }

        return {
            "session_id": first_event.session_id,
            "event_count": event_count,
            "duration_seconds": last_event.timestamp_wall - first_event.timestamp_wall,
            "start_time": first_event.timestamp_iso,
            "end_time": last_event.timestamp_iso,
            "event_types": event_types,
        }


def _make_filename() -> str:
    """Create a unique filename based on timestamp and short UUID."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    unique_id = uuid.uuid4().hex[:6]
    return f"{timestamp}_{unique_id}"


def _make_session_id() -> str:
    """Create a unique session ID."""
    return uuid.uuid4().hex[:12]


async def list_recordings(recordings_dir: Path) -> list[Dict[str, Any]]:
    """
    List all recordings in a directory with basic info.

    Args:
        recordings_dir: Directory containing recording files

    Returns:
        List of recording info dicts sorted by modification time (newest first)
    """
    recordings = []

    if not recordings_dir.exists():
        return recordings

    for path in sorted(recordings_dir.glob("*.jsonl"), reverse=True):
        stat = path.stat()
        recordings.append({
            "filename": path.name,
            "path": str(path),
            "size_bytes": stat.st_size,
            "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })

    return recordings
