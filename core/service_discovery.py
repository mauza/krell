"""
Service Discovery - Dynamic service resolution with TTL caching.

This module provides service discovery capabilities with:
- TTL-cached DNS resolution to reduce lookup overhead
- Health checks for service instances
- Automatic retry with timeout-based fallback
- Metrics integration for monitoring

Usage:
    from core.service_discovery import find_instance, async_ttl_cached

    # Find a service instance
    client = await find_instance(
        service_name="llm",
        client_factory=lambda url: LLMClient(url),
        timeout_sec=0.5,
    )

    # Use TTL caching for expensive async operations
    @async_ttl_cached(ttl_sec=0.5)
    async def resolve_service(name: str) -> str:
        return await expensive_lookup(name)
"""

import asyncio
import logging
import random
import socket
import time
from collections import defaultdict
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Hashable,
    List,
    Optional,
    Protocol,
    TypeVar,
)

from core.exceptions import ServiceAtCapacityError, ServiceTimeoutError, ServiceUnavailableError

logger = logging.getLogger(__name__)

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")
S = TypeVar("S", bound="ServiceWithStartup")


# =============================================================================
# Protocols
# =============================================================================


class ServiceWithStartup(Protocol):
    """Protocol for services that require initialization."""

    async def start_up(self) -> None:
        """
        Initialize connection to the service.

        Should raise an exception if the instance is not ready:
        - ServiceAtCapacityError: Service is full, try another
        - ServiceTimeoutError: Service didn't respond in time
        - Other exceptions: Internal errors
        """
        ...


# =============================================================================
# TTL Cached Decorator
# =============================================================================


def async_ttl_cached(
    ttl_sec: float = 0.1,
) -> Callable[[Callable[[K], Awaitable[V]]], Callable[[K], Awaitable[V]]]:
    """
    Decorator that caches async function results with a TTL.

    The cache is per-key and uses asyncio locks to prevent thundering herd.

    Args:
        ttl_sec: Time-to-live for cached values in seconds

    Returns:
        Decorated function with caching

    Usage:
        @async_ttl_cached(ttl_sec=0.5)
        async def resolve_hostname(hostname: str) -> list[str]:
            return await dns_lookup(hostname)
    """
    def decorator(func: Callable[[K], Awaitable[V]]) -> Callable[[K], Awaitable[V]]:
        cache: Dict[K, tuple[float, V]] = {}
        locks: Dict[K, asyncio.Lock] = defaultdict(asyncio.Lock)

        @wraps(func)
        async def cached(key: K) -> V:
            async with locks[key]:
                now = time.time()
                try:
                    key_time, value = cache[key]
                except KeyError:
                    pass
                else:
                    if now - key_time < ttl_sec:
                        return value

                value = await func(key)
                cache[key] = (now, value)
                return value

        return cached

    return decorator


# =============================================================================
# Stopwatch Utility
# =============================================================================


class Stopwatch:
    """Simple timing utility."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def reset(self) -> None:
        """Reset the stopwatch."""
        self._start = time.perf_counter()

    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.perf_counter() - self._start

    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return self.elapsed() * 1000


# =============================================================================
# DNS Resolution
# =============================================================================


@async_ttl_cached(ttl_sec=0.5)
async def _resolve_hostname(hostname: str) -> List[str]:
    """
    Resolve a hostname to IP addresses with TTL caching.

    Args:
        hostname: Hostname to resolve

    Returns:
        List of IP addresses
    """
    try:
        _, _, ipaddrlist = await asyncio.to_thread(socket.gethostbyname_ex, hostname)
        return list(ipaddrlist)
    except socket.gaierror as e:
        logger.warning(f"Failed to resolve hostname {hostname}: {e}")
        return []


async def get_service_instances(
    service_url: str,
    shuffle: bool = True,
) -> List[str]:
    """
    Get all available instances of a service.

    Parses the service URL, resolves the hostname to IPs, and returns
    a list of instance URLs.

    Args:
        service_url: Service URL (e.g., "http://llm-service:8000")
        shuffle: Whether to randomize the order of instances

    Returns:
        List of instance URLs with resolved IPs
    """
    # Parse URL
    if "://" not in service_url:
        service_url = f"http://{service_url}"

    protocol, remaining = service_url.split("://", 1)

    if "/" in remaining:
        host_port, path = remaining.split("/", 1)
        path = "/" + path
    else:
        host_port = remaining
        path = ""

    if ":" in host_port:
        hostname, port = host_port.split(":", 1)
    else:
        hostname = host_port
        port = "80" if protocol == "http" else "443"

    # Resolve hostname to IPs
    ips = await _resolve_hostname(hostname)

    if not ips:
        # Couldn't resolve, return original URL
        return [service_url]

    # Build instance URLs
    instances = [f"{protocol}://{ip}:{port}{path}" for ip in ips]

    if shuffle:
        random.shuffle(instances)

    return instances


# =============================================================================
# Service Discovery
# =============================================================================


async def find_instance(
    service_name: str,
    service_url: str,
    client_factory: Callable[[str], S],
    timeout_sec: float = 0.5,
    max_trials: int = 3,
) -> S:
    """
    Find an available service instance with health checking.

    Tries each instance in turn until one responds successfully.
    Uses the ServiceWithStartup protocol to verify instance health.

    Args:
        service_name: Name for logging/metrics
        service_url: Base service URL to resolve
        client_factory: Factory function that creates a client from URL
        timeout_sec: Timeout for each connection attempt
        max_trials: Maximum number of instances to try

    Returns:
        Connected client instance

    Raises:
        ServiceAtCapacityError: All instances are at capacity
        ServiceTimeoutError: All instances timed out
        ServiceUnavailableError: No instances available

    Usage:
        client = await find_instance(
            service_name="llm",
            service_url="http://llm-service:8000",
            client_factory=lambda url: LLMClient(url),
        )
    """
    stopwatch = Stopwatch()
    instances = await get_service_instances(service_url)

    if not instances:
        raise ServiceUnavailableError(service_name, cause=Exception("No instances found"))

    max_trials = min(len(instances), max_trials)
    last_exception: Optional[Exception] = None

    for instance in instances[:max_trials + 1]:
        client = client_factory(instance)
        ping_stopwatch = Stopwatch()

        logger.debug(f"[{service_name}] Trying instance: {instance}")

        try:
            async with asyncio.timeout(timeout_sec):
                await client.start_up()

        except asyncio.TimeoutError:
            max_trials -= 1
            elapsed = ping_stopwatch.elapsed_ms()
            logger.warning(
                f"[{service_name}] Instance {instance} timed out after {elapsed:.1f}ms"
            )
            last_exception = ServiceTimeoutError(service_name, timeout_sec)

            if max_trials <= 0:
                raise ServiceTimeoutError(service_name, timeout_sec) from last_exception

        except ServiceAtCapacityError:
            max_trials -= 1
            elapsed = ping_stopwatch.elapsed_ms()
            logger.info(
                f"[{service_name}] Instance {instance} at capacity ({elapsed:.1f}ms)"
            )
            last_exception = ServiceAtCapacityError(service_name)

            if max_trials <= 0:
                raise

        except Exception as exc:
            max_trials -= 1
            elapsed = ping_stopwatch.elapsed_ms()
            logger.error(
                f"[{service_name}] Unexpected error connecting to {instance}: {exc}"
            )
            last_exception = exc

            if max_trials <= 0:
                raise ServiceUnavailableError(service_name, cause=exc) from exc

        else:
            # Success!
            elapsed = ping_stopwatch.elapsed_ms()
            total_elapsed = stopwatch.elapsed_ms()
            logger.info(
                f"[{service_name}] Connected to {instance} "
                f"(ping: {elapsed:.1f}ms, total: {total_elapsed:.1f}ms)"
            )
            return client

    # Should not reach here, but just in case
    if last_exception:
        raise ServiceUnavailableError(service_name, cause=last_exception)
    raise ServiceUnavailableError(service_name)


# =============================================================================
# Service Registry
# =============================================================================


class ServiceRegistry:
    """
    Registry for service URLs and discovery settings.

    Usage:
        registry = ServiceRegistry()
        registry.register("llm", "http://llm-service:8000")
        registry.register("tts", "http://tts-service:8001")

        # Find instance
        url = registry.get_url("llm")
        instances = await get_service_instances(url)
    """

    def __init__(self) -> None:
        self._services: Dict[str, str] = {}
        self._settings: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        url: str,
        timeout_sec: float = 0.5,
        max_trials: int = 3,
    ) -> None:
        """
        Register a service.

        Args:
            name: Service name
            url: Service URL
            timeout_sec: Default timeout for this service
            max_trials: Default max trials for this service
        """
        self._services[name] = url
        self._settings[name] = {
            "timeout_sec": timeout_sec,
            "max_trials": max_trials,
        }

    def unregister(self, name: str) -> None:
        """Remove a service from the registry."""
        self._services.pop(name, None)
        self._settings.pop(name, None)

    def get_url(self, name: str) -> Optional[str]:
        """Get the URL for a service."""
        return self._services.get(name)

    def get_settings(self, name: str) -> Dict[str, Any]:
        """Get settings for a service."""
        return self._settings.get(name, {})

    def list_services(self) -> List[str]:
        """List all registered service names."""
        return list(self._services.keys())

    async def find_instance(
        self,
        name: str,
        client_factory: Callable[[str], S],
        timeout_sec: Optional[float] = None,
        max_trials: Optional[int] = None,
    ) -> S:
        """
        Find an instance of a registered service.

        Args:
            name: Service name
            client_factory: Factory for creating clients
            timeout_sec: Override timeout
            max_trials: Override max trials

        Returns:
            Connected client

        Raises:
            ValueError: If service not registered
            ServiceUnavailableError: If no instances available
        """
        url = self.get_url(name)
        if not url:
            raise ValueError(f"Service not registered: {name}")

        settings = self.get_settings(name)

        return await find_instance(
            service_name=name,
            service_url=url,
            client_factory=client_factory,
            timeout_sec=timeout_sec or settings.get("timeout_sec", 0.5),
            max_trials=max_trials or settings.get("max_trials", 3),
        )


# Global registry instance
_registry = ServiceRegistry()


def get_registry() -> ServiceRegistry:
    """Get the global service registry."""
    return _registry
