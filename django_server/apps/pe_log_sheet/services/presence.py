import threading
import time
from copy import deepcopy


DEFAULT_DOCUMENT_ID = "main"
PRESENCE_TTL_SECONDS = 10


class PresenceRegistry:
    def __init__(self):
        self._entries: dict[str, dict[str, dict]] = {}
        self._lock = threading.Lock()

    def _prune_locked(self, now: float, document_id: str):
        doc_entries = self._entries.get(document_id, {})
        expired = [
            client_id
            for client_id, entry in doc_entries.items()
            if now - entry["last_seen"] > PRESENCE_TTL_SECONDS
        ]
        for client_id in expired:
            doc_entries.pop(client_id, None)
        if not doc_entries:
            self._entries.pop(document_id, None)

    def _snapshot_locked(self, document_id: str) -> list[dict]:
        doc_entries = self._entries.get(document_id, {})
        users = {}
        for entry in doc_entries.values():
            username = entry["username"]
            if username not in users:
                users[username] = {
                    "username": username,
                    "display_name": entry["display_name"],
                }
        return sorted(users.values(), key=lambda item: item["username"])

    def join(self, document_id: str, client_id: str, user) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            doc_entries = self._entries.setdefault(document_id, {})
            doc_entries[client_id] = {
                "client_id": client_id,
                "username": user.username,
                "display_name": user.username,
                "last_seen": now,
            }
            self._prune_locked(now, document_id)
            return deepcopy(self._snapshot_locked(document_id))

    def heartbeat(
        self, document_id: str, client_id: str, user
    ) -> tuple[list[dict], bool]:
        now = time.monotonic()
        with self._lock:
            doc_entries = self._entries.get(document_id, {})
            before = set(doc_entries.keys())
            self._prune_locked(now, document_id)
            doc_entries = self._entries.get(document_id, {})
            entry = doc_entries.get(client_id)
            if entry:
                entry["username"] = user.username
                entry["display_name"] = user.username
                entry["last_seen"] = now
            after = set(doc_entries.keys())
            return deepcopy(self._snapshot_locked(document_id)), before != after

    def leave(self, document_id: str, client_id: str) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            doc_entries = self._entries.get(document_id, {})
            doc_entries.pop(client_id, None)
            self._prune_locked(now, document_id)
            return deepcopy(self._snapshot_locked(document_id))

    def snapshot(self, document_id: str) -> list[dict]:
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now, document_id)
            return deepcopy(self._snapshot_locked(document_id))

    def reset(self):
        with self._lock:
            self._entries.clear()


_registry = PresenceRegistry()


def get_presence_registry() -> PresenceRegistry:
    return _registry
