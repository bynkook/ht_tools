import logging
import threading
import time
from copy import deepcopy

DEFAULT_DOCUMENT_ID = "main"
CELL_LOCK_TTL_SECONDS = 30

logger = logging.getLogger(__name__)


class CellLockRegistry:
    """Thread-safe, document-scoped in-memory registry for cell soft-locks.

    Each client may hold at most one active cell lock per document at a time
    (phase-1 constraint). Acquiring a new cell atomically releases the
    previous one.

    Lock entries expire after CELL_LOCK_TTL_SECONDS (60 s) and are pruned
    on every access.
    """

    def __init__(self):
        # {document_id: {client_id: lock_entry}}
        self._entries: dict[str, dict[str, dict]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers (must be called while self._lock is held)
    # ------------------------------------------------------------------

    def _prune_locked(self, now: float, document_id: str) -> None:
        """Remove expired lock entries for *document_id*."""
        doc_entries = self._entries.get(document_id, {})
        expired = [
            client_id
            for client_id, entry in doc_entries.items()
            if now - entry["last_seen"] > CELL_LOCK_TTL_SECONDS
        ]
        for client_id in expired:
            doc_entries.pop(client_id, None)
        if not doc_entries:
            self._entries.pop(document_id, None)

    def _cell_key(self, sheet_id: str, row: int, column: int) -> str:
        """Return a deterministic key for a cell position."""
        return f"{sheet_id}:{row}:{column}"

    def _find_owner_entry(
        self, document_id: str, sheet_id: str, row: int, column: int
    ) -> dict | None:
        """Return the lock entry that owns the given cell, or None."""
        doc_entries = self._entries.get(document_id, {})
        cell_key = self._cell_key(sheet_id, row, column)
        for entry in doc_entries.values():
            if entry["_cell_key"] == cell_key:
                return entry
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def acquire(
        self,
        document_id: str,
        sheet_id: str,
        row: int,
        column: int,
        client_id: str,
        user,
    ) -> tuple[dict, bool]:
        """Attempt to acquire a cell lock.

        Returns ``(lock_info, is_new)`` where:

        * Same cell + same client  → idempotent refresh, ``(lock_info, False)``
        * Same client + different cell → atomic move, ``(lock_info, True)``
        * Different client + locked cell → ``(locked_by_info, False)``
        * Different client + unlocked cell → acquire, ``(lock_info, True)``
        """
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now, document_id)
            doc_entries = self._entries.setdefault(document_id, {})

            # 1) Same client already holds a lock — check if same cell
            existing = doc_entries.get(client_id)
            if existing is not None:
                existing_cell_key = existing["_cell_key"]
                new_cell_key = self._cell_key(sheet_id, row, column)

                if existing_cell_key == new_cell_key:
                    # Idempotent: same cell, same client — just refresh
                    existing["last_seen"] = now
                    return deepcopy(existing), False

                # Atomic move: release previous cell, acquire new one
                del doc_entries[client_id]

            # 2) Check if another client holds this cell
            owner = self._find_owner_entry(document_id, sheet_id, row, column)
            if owner is not None:
                # Cell is locked by someone else — return owner info without mutation
                return deepcopy(owner), False

            # 3) Cell is free — acquire it
            lock_entry = {
                "document_id": document_id,
                "sheet_id": sheet_id,
                "row": row,
                "column": column,
                "client_id": client_id,
                "username": user.username,
                "display_name": user.username,
                "last_seen": now,
                "_cell_key": self._cell_key(sheet_id, row, column),
            }
            doc_entries[client_id] = lock_entry
            return deepcopy(lock_entry), True

    def heartbeat(
        self,
        document_id: str,
        client_id: str,
        sheet_id: str,
        row: int,
        column: int,
    ) -> tuple[dict | None, bool]:
        """Refresh ``last_seen`` for a self-owned lock.

        Returns ``(lock_info, True)`` if the client owns the specified cell
        and the heartbeat was refreshed.  Returns ``(None, False)`` if the
        client does not own this cell (wrong cell, expired, or never held).
        """
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now, document_id)
            doc_entries = self._entries.get(document_id, {})
            entry = doc_entries.get(client_id)
            if entry is None:
                return None, False

            # Verify the client still owns the *same* cell
            expected_cell_key = self._cell_key(sheet_id, row, column)
            if entry["_cell_key"] != expected_cell_key:
                return None, False

            entry["last_seen"] = now
            return deepcopy(entry), True

    def release(
        self,
        document_id: str,
        client_id: str,
        sheet_id: str,
        row: int,
        column: int,
    ) -> None:
        """Remove a self-owned lock. Harmless if the client owns a different
        cell or no lock at all."""
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now, document_id)
            doc_entries = self._entries.get(document_id, {})
            entry = doc_entries.get(client_id)
            if entry is None:
                return

            # Only release if the cell matches
            expected_cell_key = self._cell_key(sheet_id, row, column)
            if entry["_cell_key"] == expected_cell_key:
                del doc_entries[client_id]
                if not doc_entries:
                    self._entries.pop(document_id, None)

    def release_all(self, document_id: str, client_id: str) -> None:
        """Remove every lock held by *client_id* in *document_id*."""
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now, document_id)
            doc_entries = self._entries.get(document_id, {})
            doc_entries.pop(client_id, None)
            if not doc_entries:
                self._entries.pop(document_id, None)

    def owner_for_cell(
        self, document_id: str, sheet_id: str, row: int, column: int
    ) -> dict | None:
        """Return owner info for a locked cell, or ``None`` if unlocked."""
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now, document_id)
            owner = self._find_owner_entry(document_id, sheet_id, row, column)
            if owner is None:
                return None
            return deepcopy(owner)

    def snapshot(self, document_id: str) -> list[dict]:
        """Return a list of all active locks in the document."""
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now, document_id)
            doc_entries = self._entries.get(document_id, {})
            return [deepcopy(entry) for entry in doc_entries.values()]

    def reset(self) -> None:
        """Clear all entries (for testing)."""
        with self._lock:
            self._entries.clear()


_registry = CellLockRegistry()


def get_cell_lock_registry() -> CellLockRegistry:
    return _registry
