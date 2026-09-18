"""Cache layer wrapper around SqliteCache."""

from __future__ import annotations

from openbundle.adapters.sqlite_cache import SqliteCache, exact_key
from openbundle.config import Settings
from openbundle.pipeline.types import InternalRequest, InternalResponse


class CacheLayer:
    name = "cache"

    def __init__(self, settings: Settings, store: SqliteCache | None = None) -> None:
        self.settings = settings
        self.enabled = settings.layers.cache.enabled
        self.semantic = settings.layers.cache.semantic
        self.store = store or SqliteCache(
            settings.cache_path(),
            semantic=self.semantic,
            threshold=settings.layers.cache.semantic_threshold,
        )

    def lookup(self, request: InternalRequest) -> InternalResponse | None:
        if not self.enabled:
            return None
        key = exact_key(request)
        hit = self.store.get(key)
        if hit:
            return hit
        return None

    def store_response(self, request: InternalRequest, response: InternalResponse) -> None:
        if not self.enabled:
            return
        self.store.put(exact_key(request), request, response)
