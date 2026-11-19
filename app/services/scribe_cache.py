"""ScribeCache — In-memory transcript accumulator for voice scribe sessions.

Keyed by (user_id, patient_id). Entries expire after ttl_minutes of inactivity.
Thread-safe via a module-level Lock. Cleanup runs at most once every 5 minutes.

Usage:
    from app.services.scribe_cache import scribe_cache

    scribe_cache.append(user_id, patient_id, new_text)
    full_text = scribe_cache.get(user_id, patient_id)
    scribe_cache.clear(user_id, patient_id)
"""
import threading
from datetime import datetime, timedelta
from typing import Optional


class ScribeCache:
    def __init__(self, ttl_minutes: int = 30):
        self._store: dict = {}
        self._lock = threading.Lock()
        self._ttl = timedelta(minutes=ttl_minutes)
        self._last_cleanup: Optional[datetime] = None

    def append(self, user_id: int, patient_id: int, text: str) -> None:
        self._cleanup_if_due()
        key = self._make_key(user_id, patient_id)
        with self._lock:
            existing = self._store.get(key, {}).get('content', '')
            joined = (existing + '\n\n' + text).strip() if existing else text.strip()
            self._store[key] = {'content': joined, 'updated_at': datetime.utcnow()}

    def set(self, user_id: int, patient_id: int, content: str) -> None:
        self._cleanup_if_due()
        key = self._make_key(user_id, patient_id)
        with self._lock:
            self._store[key] = {'content': content, 'updated_at': datetime.utcnow()}

    def get(self, user_id: int, patient_id: int) -> str:
        self._cleanup_if_due()
        key = self._make_key(user_id, patient_id)
        with self._lock:
            entry = self._store.get(key)
            if entry and self._is_alive(entry):
                return entry['content']
            return ''

    def clear(self, user_id: int, patient_id: int) -> None:
        self._cleanup_if_due()
        key = self._make_key(user_id, patient_id)
        with self._lock:
            self._store.pop(key, None)

    def has_content(self, user_id: int, patient_id: int) -> bool:
        return bool(self.get(user_id, patient_id))

    def get_stats(self, user_id: int, patient_id: int) -> Optional[dict]:
        key = self._make_key(user_id, patient_id)
        with self._lock:
            entry = self._store.get(key)
            if not entry or not self._is_alive(entry):
                return None
            content = entry['content']
            return {
                'char_count': len(content),
                'word_count': len(content.split()),
                'last_updated': entry['updated_at'].isoformat(),
            }

    @staticmethod
    def _make_key(user_id: int, patient_id: int) -> str:
        return f"{user_id}:{patient_id}"

    def _is_alive(self, entry: dict) -> bool:
        return (datetime.utcnow() - entry['updated_at']) < self._ttl

    def _cleanup_if_due(self) -> None:
        now = datetime.utcnow()
        if self._last_cleanup and (now - self._last_cleanup) < timedelta(minutes=5):
            return
        with self._lock:
            if self._last_cleanup and (now - self._last_cleanup) < timedelta(minutes=5):
                return
            expired = [k for k, v in self._store.items() if not self._is_alive(v)]
            for k in expired:
                del self._store[k]
            self._last_cleanup = now


scribe_cache = ScribeCache(ttl_minutes=30)
