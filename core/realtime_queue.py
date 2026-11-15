"""
Real-time Queue - Heap-based timed release for synchronized audio/text.

This module provides a queue that releases items at their scheduled times,
enabling precise synchronization between text display and audio playback.

The problem it solves:
- TTS generates audio faster than real-time (e.g., 2x real-time speed)
- Without timing control, audio would play too fast
- Text and audio timestamps need to stay synchronized

Usage:
    from core.realtime_queue import RealtimeQueue

    queue = RealtimeQueue()

    # Add items with target release times
    queue.put(audio_chunk_1, time=0.0)    # Play immediately
    queue.put(audio_chunk_2, time=0.32)   # Play after 320ms
    queue.put(text_update, time=0.5)      # Show text at 500ms

    # Get items when their time has come
    async for release_time, item in queue.get():
        process(item)
"""

import asyncio
import heapq
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Generic, List, Optional, Tuple, TypeVar

T = TypeVar("T")


@dataclass(order=True)
class TimedItem(Generic[T]):
    """An item with a scheduled release time."""

    time: float
    item: T = field(compare=False)

    def as_tuple(self) -> Tuple[float, T]:
        return (self.time, self.item)


class RealtimeQueue(Generic[T]):
    """
    A priority queue that releases items at their scheduled times.

    Items are stored in a min-heap ordered by release time. The get() method
    waits until items are due before yielding them.

    This enables:
    - Audio buffering (prevent playback speedup)
    - Text/audio synchronization
    - Precise timing control for streaming

    Attributes:
        queue: Heap of TimedItem objects
        start_time: Reference time for scheduling (set on first put)
    """

    def __init__(self, get_time: Optional[Callable[[], float]] = None):
        """
        Initialize the queue.

        Args:
            get_time: Optional custom time function (defaults to time.time)
        """
        self.queue: List[TimedItem[T]] = []
        self.start_time: Optional[float] = None
        self.get_time = get_time or time.time
        self._closed = False

    def put(self, item: T, release_time: float) -> None:
        """
        Add an item to be released at the specified time.

        Args:
            item: The item to queue
            release_time: When to release (seconds from queue start)
        """
        if self.start_time is None:
            self.start_time = self.get_time()

        heapq.heappush(self.queue, TimedItem(release_time, item))

    def put_nowait(self, item: T) -> None:
        """Add an item to be released immediately."""
        if self.start_time is None:
            self.start_time = self.get_time()

        # Use current elapsed time for immediate release
        elapsed = self.get_time() - self.start_time
        heapq.heappush(self.queue, TimedItem(elapsed, item))

    async def get(self) -> AsyncIterator[Tuple[float, T]]:
        """
        Async generator that yields items when their time has come.

        Waits precisely until each item's scheduled time before yielding.
        Items are yielded in time order (earliest first).

        Yields:
            Tuple of (release_time, item)
        """
        while self.queue and not self._closed:
            if self.start_time is None:
                await asyncio.sleep(0.001)
                continue

            elapsed = self.get_time() - self.start_time
            next_item = self.queue[0]
            delta = next_item.time - elapsed

            if delta > 0:
                # Wait until this item is due
                await asyncio.sleep(delta)

            # Pop and yield the item
            item = heapq.heappop(self.queue)
            yield item.as_tuple()

    def get_nowait(self) -> List[Tuple[float, T]]:
        """
        Get all items that are past due without waiting.

        Returns:
            List of (release_time, item) tuples for items past due
        """
        if self.start_time is None:
            return []

        elapsed = self.get_time() - self.start_time
        ready = []

        while self.queue and self.queue[0].time <= elapsed:
            item = heapq.heappop(self.queue)
            ready.append(item.as_tuple())

        return ready

    def peek_next_time(self) -> Optional[float]:
        """Get the release time of the next item without removing it."""
        if not self.queue:
            return None
        return self.queue[0].time

    def clear(self) -> None:
        """Clear all pending items."""
        self.queue.clear()

    def close(self) -> None:
        """Close the queue, causing get() to stop iteration."""
        self._closed = True

    @property
    def size(self) -> int:
        """Number of items in the queue."""
        return len(self.queue)

    @property
    def is_empty(self) -> bool:
        """Whether the queue is empty."""
        return len(self.queue) == 0

    @property
    def elapsed(self) -> float:
        """Seconds since queue started."""
        if self.start_time is None:
            return 0.0
        return self.get_time() - self.start_time


# Audio buffer constant (matches unmute)
# TTS generates faster than real-time, so we delay audio by this amount
# to prevent playback speedup and allow text/audio sync
AUDIO_BUFFER_SEC = 0.32  # 320ms = 4 frames at 80ms/frame
