"""
Quest Manager - RAII-style async resource management for task lifecycle.

This module provides a pattern for managing the lifecycle of long-running async
operations with guaranteed cleanup, inspired by the Unmute project.

A Quest represents an async unit of work consisting of:
- An init step that returns a resource of type T
- A run step that uses the resource
- A close step that cleans up the resource

Usage:
    async with QuestManager() as manager:
        quest = Quest(
            name="tts_stream",
            init=lambda: tts_service.connect(),
            run=lambda conn: stream_audio(conn),
            close=lambda conn: conn.disconnect(),
        )
        await manager.add(quest)
        await manager.wait()  # Wait for all quests to complete
"""

import asyncio
import logging
import types
from collections.abc import Awaitable
from functools import partial
from typing import Any, Callable, Generic, TypeVar

from core.exceptions import (
    ConnectionClosedError,
    ServiceAtCapacityError,
    ServiceTimeoutError,
)

T = TypeVar("T")
logger = logging.getLogger(__name__)


class Quest(Generic[T]):
    """
    A Quest is an async unit of work with init, run, and close phases.

    It can be used as an async context manager for guaranteed cleanup.
    Should be used with QuestManager for managing multiple quests.

    Type Parameters:
        T: The type of resource created by the init step

    Attributes:
        name: Identifier for this quest (used for logging and manager lookup)
        init: Async callable that creates and returns the resource
        run: Async callable that uses the resource
        close: Optional async callable for cleanup
    """

    def __init__(
        self,
        name: str,
        init: Callable[[], Awaitable[T]],
        run: Callable[[T], Awaitable[None]],
        close: Callable[[T], Awaitable[None]] | None = None,
    ):
        """
        Initialize a Quest.

        Args:
            name: Identifier for this quest
            init: Async function that creates the resource
            run: Async function that uses the resource
            close: Optional async function to clean up the resource
        """
        self.name = name
        self.init = init
        self.run = run
        self.close = close
        self.task: asyncio.Task[None] | None = None
        self._data: asyncio.Future[T] = asyncio.get_event_loop().create_future()

    @staticmethod
    def from_run_step(name: str, run: Callable[[], Awaitable[None]]) -> "Quest[None]":
        """
        Create a Quest from just a run step (no init/close needed).

        Useful for simple async operations that don't need resource management.

        Args:
            name: Identifier for this quest
            run: Async function to run

        Returns:
            Quest with no-op init and no close
        """

        async def _init() -> None:
            return None

        async def _run(_x: None) -> None:
            await run()

        return Quest(name, _init, _run)

    async def get(self) -> T:
        """
        Get the resource created by init.

        Blocks until init completes. Raises if init failed.

        Returns:
            The resource created by init

        Raises:
            Exception: If init raised an exception
        """
        return await self._data

    def get_nowait(self) -> T | None:
        """
        Get the resource without waiting.

        Returns:
            The resource if init is complete, None otherwise
        """
        if self._data.done() and not self._data.cancelled():
            try:
                return self._data.result()
            except Exception:
                return None
        return None

    async def _run_quest(self) -> None:
        """Internal method that runs the init and run phases."""
        logger.debug("Quest %s init starting...", self.name)
        try:
            data = await self.init()
        except Exception as exc:
            if not self._data.done():
                self._data.set_exception(exc)
            raise
        else:
            if not self._data.done():
                self._data.set_result(data)
        logger.debug("Quest %s running...", self.name)
        await self.run(data)

    async def __aenter__(self) -> asyncio.Future[None]:
        """
        Start the quest as a background task.

        Returns:
            Future that completes when the quest finishes
        """
        self.task = asyncio.create_task(self._run_quest())
        return asyncio.ensure_future(self.task)

    async def __aexit__(self, *exc: Any) -> None:
        """Clean up the quest on context exit."""
        await self.remove()

    async def remove(self) -> None:
        """
        Cancel the quest and run cleanup.

        This method:
        1. Runs the close callback if init succeeded
        2. Cancels the running task

        Safe to call multiple times.
        """
        if self.task is None:
            return

        try:
            if self.close is not None:
                # Only run close if init succeeded
                logger.debug("Quest %s closing...", self.name)
                try:
                    if self._data.done() and not self._data.cancelled():
                        try:
                            self._data.exception()  # Check for exception
                        except Exception:
                            pass  # Init failed, don't run close
                        else:
                            await self.close(await self.get())
                except asyncio.CancelledError:
                    pass
                self.close = None
        finally:
            logger.debug("Quest %s canceling...", self.name)
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass


class QuestManager:
    """
    Manages multiple Quests with automatic cleanup.

    Quests with the same name will replace previous quests (canceling them).
    Use wait() to propagate exceptions from any quest.

    Usage:
        async with QuestManager() as manager:
            await manager.add(quest1)
            await manager.add(quest2)

            # Optional: wait for quests and propagate exceptions
            await asyncio.gather(
                manager.wait(),
                some_other_task(),
            )
    """

    def __init__(self) -> None:
        """Initialize the QuestManager."""
        self.quests: dict[str, Quest[Any]] = {}
        self._future: asyncio.Future[None] | None = None

    async def wait(self) -> None:
        """
        Wait for all quests to complete.

        If any quest raises an exception, it will be propagated here.

        Raises:
            Exception: If any quest fails
        """
        if self._future is None:
            raise RuntimeError("QuestManager not entered as context manager")
        await self._future

    async def add(self, quest: Quest[T]) -> Quest[T]:
        """
        Add a quest to the manager.

        If a quest with the same name exists, it will be canceled first.

        Args:
            quest: The quest to add

        Returns:
            The added quest

        Raises:
            RuntimeError: If manager not entered as context manager
        """
        if self._future is None:
            raise RuntimeError("QuestManager not entered as context manager")

        name = quest.name

        # Cancel existing quest with same name
        if name in self.quests:
            old = self.quests[name]
            await old.__aexit__(None, None, None)

        self.quests[name] = quest
        future = await quest.__aenter__()
        future.add_done_callback(partial(self._one_is_done, name, self._future))
        return quest

    async def remove(self, name: str) -> None:
        """
        Remove and cancel a quest by name.

        Safe to call if quest doesn't exist.

        Args:
            name: Name of the quest to remove
        """
        quest = self.quests.pop(name, None)
        if quest is not None:
            await quest.remove()

    @staticmethod
    def _one_is_done(
        name: str, agg_future: asyncio.Future[None], future: asyncio.Future[None]
    ) -> None:
        """Callback when a quest completes."""
        logger.debug("Quest %s is done.", name)
        try:
            future.result()
        except asyncio.CancelledError:
            logger.debug("Quest %s was cancelled.", name)
        except Exception as exc:
            logger.debug("Quest %s failed with %r.", name, exc)
            if not agg_future.done():
                agg_future.set_exception(exc)

    async def __aenter__(self) -> "QuestManager":
        """Enter the manager context."""
        if self._future is not None:
            raise RuntimeError("QuestManager already entered")
        logger.debug("Quest manager entering...")
        self._future = asyncio.get_event_loop().create_future()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Exit the manager context and clean up all quests."""
        if self._future is None:
            return

        logger.debug("Quest manager exiting...")
        for name, quest in list(self.quests.items()):
            try:
                await quest.remove()
            except (
                ServiceAtCapacityError,
                ServiceTimeoutError,
                ConnectionClosedError,
            ):
                pass
            except Exception:
                logger.exception(f"Error shutting down quest {name}.")

        logger.debug("All quests canceled...")
        self.quests.clear()

        if not self._future.done():
            self._future.set_result(None)
        self._future = None
