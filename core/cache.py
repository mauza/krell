"""
Cache Abstraction - Redis/local cache with graceful fallback.

This module provides a unified caching interface with:
- Local in-memory cache with TTL support
- Optional Redis backend for production deployments
- Automatic fallback to local cache if Redis unavailable
- Generic type support for cached values

Usage:
    from core.cache import get_cache, LocalCache, RedisCache

    # Get the best available cache
    cache = get_cache(prefix="krell", ttl_seconds=3600)

    # Use the cache
    cache.set("key", b"value")
    value = cache.get("key")

    # With type hints
    cache: LocalCache[bytes] = LocalCache(ttl_seconds=300)
"""

import logging
import os
import time
from typing import Generic, Optional, TypeVar, Union, cast

logger = logging.getLogger(__name__)

# Generic type for cached values
T = TypeVar("T")


class CacheError(Exception):
    """
    Base exception for cache operations.

    Provides consistent exception type across cache implementations.
    """

    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.cause = cause


class LocalCache(Generic[T]):
    """
    In-memory cache with TTL support.

    This is a simple dict-based cache that stores values with expiration
    timestamps. Suitable for single-process deployments.

    Attributes:
        ttl_seconds: Default time-to-live for cached values
    """

    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize the local cache.

        Args:
            ttl_seconds: Default TTL in seconds (default: 1 hour)
        """
        self.cache: dict[str, tuple[T, float]] = {}  # {key: (value, expiration_timestamp)}
        self.ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[T]:
        """
        Get a value from the cache.

        Returns None if the key doesn't exist or has expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        cached = self.cache.get(key)
        if cached is not None:
            value, expiration = cached
            if time.time() < expiration:
                self._hits += 1
                return value
            else:
                # Remove expired entry
                del self.cache[key]
                self._misses += 1
                return None
        self._misses += 1
        return None

    def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL override (uses default if not provided)
        """
        ttl_seconds = ttl if ttl is not None else self.ttl_seconds
        expiration = time.time() + ttl_seconds
        self.cache[key] = (value, expiration)

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False if not found
        """
        if key in self.cache:
            del self.cache[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        """
        Check if a key exists and is not expired.

        Args:
            key: Cache key to check

        Returns:
            True if key exists and is valid
        """
        return self.get(key) is not None

    def cleanup(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns:
            Number of entries removed
        """
        now = time.time()
        expired_keys = [k for k, (_, exp) in self.cache.items() if exp < now]
        for k in expired_keys:
            del self.cache[k]
        return len(expired_keys)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self.cache.clear()

    @property
    def size(self) -> int:
        """Number of entries in the cache (including possibly expired)."""
        return len(self.cache)

    @property
    def stats(self) -> dict:
        """Cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": self.size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


class RedisCache(Generic[T]):
    """
    Redis-backed cache with TTL support.

    Provides distributed caching for multi-process or multi-server deployments.
    Falls back gracefully if Redis is unavailable.

    Attributes:
        ttl_seconds: Default time-to-live for cached values
        prefix: Key prefix to namespace cache entries
    """

    def __init__(
        self,
        redis_url: str,
        prefix: str = "krell",
        ttl_seconds: int = 3600,
        socket_timeout: float = 2.0,
    ):
        """
        Initialize the Redis cache.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379")
            prefix: Key prefix for namespacing
            ttl_seconds: Default TTL in seconds
            socket_timeout: Connection timeout in seconds
        """
        import redis

        self.ttl_seconds = ttl_seconds
        self.prefix = prefix
        self._hits = 0
        self._misses = 0

        try:
            self.redis_client = redis.Redis.from_url(
                redis_url,
                socket_connect_timeout=socket_timeout,
                socket_timeout=socket_timeout,
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Connected to Redis at {redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise CacheError(f"Failed to connect to Redis: {e}", cause=e)

    def _make_key(self, key: str) -> str:
        """Create a prefixed key."""
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Optional[T]:
        """
        Get a value from Redis.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found

        Raises:
            CacheError: If Redis operation fails
        """
        import redis

        try:
            redis_key = self._make_key(key)
            value = self.redis_client.get(redis_key)
            if value is not None:
                self._hits += 1
                return cast(T, value)
            self._misses += 1
            return None
        except redis.RedisError as e:
            raise CacheError(f"Failed to get value from Redis: {e}", cause=e)

    def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """
        Set a value in Redis with TTL.

        Args:
            key: Cache key
            value: Value to cache (must be bytes-compatible)
            ttl: Optional TTL override

        Raises:
            CacheError: If Redis operation fails
        """
        import redis

        try:
            redis_key = self._make_key(key)
            ttl_seconds = ttl if ttl is not None else self.ttl_seconds
            self.redis_client.setex(redis_key, ttl_seconds, value)  # type: ignore
        except redis.RedisError as e:
            raise CacheError(f"Failed to set value in Redis: {e}", cause=e)

    def delete(self, key: str) -> bool:
        """
        Delete a key from Redis.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted

        Raises:
            CacheError: If Redis operation fails
        """
        import redis

        try:
            redis_key = self._make_key(key)
            result = self.redis_client.delete(redis_key)
            return result > 0
        except redis.RedisError as e:
            raise CacheError(f"Failed to delete value from Redis: {e}", cause=e)

    def exists(self, key: str) -> bool:
        """
        Check if a key exists in Redis.

        Args:
            key: Cache key to check

        Returns:
            True if key exists

        Raises:
            CacheError: If Redis operation fails
        """
        import redis

        try:
            redis_key = self._make_key(key)
            return bool(self.redis_client.exists(redis_key))
        except redis.RedisError as e:
            raise CacheError(f"Failed to check key existence in Redis: {e}", cause=e)

    def cleanup(self) -> int:
        """
        Cleanup is automatic with Redis TTL.

        Returns:
            0 (no manual cleanup needed)
        """
        return 0

    def clear(self) -> None:
        """
        Clear all entries with this prefix.

        Warning: This scans all keys, use with caution in production.
        """
        import redis

        try:
            pattern = self._make_key("*")
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
        except redis.RedisError as e:
            raise CacheError(f"Failed to clear cache: {e}", cause=e)

    @property
    def stats(self) -> dict:
        """Cache statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


# Type alias for either cache implementation
Cache = Union[LocalCache[T], RedisCache[T]]


def get_cache(
    prefix: str = "krell",
    ttl_seconds: int = 3600,
    redis_url: Optional[str] = None,
) -> Union[LocalCache[bytes], RedisCache[bytes]]:
    """
    Get the best available cache implementation.

    Attempts to connect to Redis if a URL is provided. Falls back to
    local in-memory cache if Redis is unavailable or not configured.

    Args:
        prefix: Key prefix for namespacing
        ttl_seconds: Default TTL for cached values
        redis_url: Optional Redis URL (also checks KRELL_REDIS_URL env var)

    Returns:
        Cache instance (either RedisCache or LocalCache)
    """
    # Check environment variable if no URL provided
    url = redis_url or os.getenv("KRELL_REDIS_URL")

    if url:
        try:
            return RedisCache[bytes](url, prefix=prefix, ttl_seconds=ttl_seconds)
        except CacheError:
            logger.warning("Redis unavailable, falling back to local cache")

    logger.info("Using local in-memory cache")
    return LocalCache[bytes](ttl_seconds=ttl_seconds)


class AsyncLocalCache(Generic[T]):
    """
    Async wrapper around LocalCache for consistency with async APIs.

    This is a thin async wrapper that delegates to the synchronous LocalCache.
    Useful when you want to use the same interface with both sync and async code.
    """

    def __init__(self, ttl_seconds: int = 3600):
        """Initialize with a synchronous LocalCache."""
        self._cache = LocalCache[T](ttl_seconds=ttl_seconds)

    async def get(self, key: str) -> Optional[T]:
        """Get a value from the cache."""
        return self._cache.get(key)

    async def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """Set a value in the cache."""
        self._cache.set(key, value, ttl)

    async def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        return self._cache.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return self._cache.exists(key)

    async def cleanup(self) -> int:
        """Remove expired entries."""
        return self._cache.cleanup()

    async def clear(self) -> None:
        """Clear all entries."""
        self._cache.clear()

    @property
    def stats(self) -> dict:
        """Cache statistics."""
        return self._cache.stats
