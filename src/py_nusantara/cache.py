import time
import json
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Tuple


class BaseCache(ABC):
    """Abstract base class for all cache backends."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int) -> None:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass

    def remember(self, key: str, ttl: int, callback: Callable[[], Any]) -> Any:
        """Get item from cache, or evaluate callback and store it if not cached."""
        value = self.get(key)
        if value is not None:
            return value

        computed_value = callback()
        self.set(key, computed_value, ttl)
        return computed_value


class NoCache(BaseCache):
    """Fallback cache that does not cache anything."""

    def get(self, key: str) -> Optional[Any]:
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        pass

    def clear(self) -> None:
        pass


class InMemoryCache(BaseCache):
    """Simple in-memory cache with TTL support."""

    def __init__(self) -> None:
        # Structure: key -> (value, expiry_time)
        self._store: Dict[str, Tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        value, expiry = self._store[key]
        if time.time() > expiry:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        expiry = time.time() + ttl
        self._store[key] = (value, expiry)

    def clear(self) -> None:
        self._store.clear()


class RedisCache(BaseCache):
    """Redis-backed cache with TTL support."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        try:
            import redis
            self._client = redis.from_url(redis_url, decode_responses=True)
        except ImportError:
            raise ImportError(
                "The 'redis' package is required to use RedisCache. "
                "Install it with: pip install py-nusantara[redis] or uv add redis"
            )

    def get(self, key: str) -> Optional[Any]:
        try:
            val = self._client.get(key)
            if val is not None:
                return json.loads(val)
        except Exception:
            pass
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        try:
            serialized = json.dumps(value)
            self._client.setex(key, ttl, serialized)
        except Exception:
            pass

    def clear(self) -> None:
        try:
            # Note: clears only keys matching the connection context if possible, 
            # but to flush everything cleanly:
            self._client.flushdb()
        except Exception:
            pass
