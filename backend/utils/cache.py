# utils/cache.py
"""
Caching utilities for search results and other data.
"""

import hashlib
import time
from typing import Dict, Optional, Any, TypeVar, Generic
from collections import OrderedDict
from datetime import datetime, timedelta

T = TypeVar('T')


class LRUCache(Generic[T]):
    """
    Simple LRU cache with TTL support.
    Thread-safe for single-threaded async use.
    """
    
    def __init__(self, max_size: int = 100, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, tuple[T, float]] = OrderedDict()
    
    def get(self, key: str) -> Optional[T]:
        """Get item from cache, None if not found or expired"""
        if key not in self._cache:
            return None
        
        value, timestamp = self._cache[key]
        
        # Check TTL
        if time.time() - timestamp > self.ttl_seconds:
            del self._cache[key]
            return None
        
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return value
    
    def set(self, key: str, value: T) -> None:
        """Set item in cache"""
        # Remove oldest if at capacity
        while len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)
        
        self._cache[key] = (value, time.time())
    
    def delete(self, key: str) -> bool:
        """Delete item from cache"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all items"""
        self._cache.clear()
    
    def __len__(self) -> int:
        return len(self._cache)
    
    def prune_expired(self) -> int:
        """Remove all expired items, return count removed"""
        now = time.time()
        expired = [k for k, (v, ts) in self._cache.items() if now - ts > self.ttl_seconds]
        for key in expired:
            del self._cache[key]
        return len(expired)


class SearchCache:
    """
    Specialized cache for search results.
    Uses MD5 hash of query as key.
    """
    
    def __init__(self, max_size: int = 500, ttl_hours: int = 24):
        self._cache = LRUCache[list](max_size=max_size, ttl_seconds=ttl_hours * 3600)
    
    @staticmethod
    def _query_key(query: str) -> str:
        """Generate cache key from query"""
        normalized = query.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def get(self, query: str) -> Optional[list]:
        """Get cached search results"""
        key = self._query_key(query)
        result = self._cache.get(key)
        if result:
            print(f"[CACHE] Hit for query: {query[:50]}...")
        return result
    
    def set(self, query: str, results: list) -> None:
        """Cache search results"""
        key = self._query_key(query)
        self._cache.set(key, results)
        print(f"[CACHE] Stored {len(results)} results for: {query[:50]}...")
    
    def clear(self) -> None:
        """Clear all cached results"""
        self._cache.clear()
        print("[CACHE] Cleared all search cache")
    
    def __len__(self) -> int:
        return len(self._cache)


# Global cache instances
search_cache = SearchCache()
