import threading
from queue import Queue, Empty


class StreamHub:
    """Thread-safe in-process SSE subscriber hub.

    Each subscriber holds a Queue. On commit, broadcast() puts an event
    into all queues. The SSE view generator reads from the queue with a
    timeout to emit periodic heartbeats.
    """

    def __init__(self):
        self._subscribers: set = set()
        self._lock = threading.Lock()

    def subscribe(self) -> Queue:
        q: Queue = Queue(maxsize=200)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: Queue) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def broadcast(self, event_data: dict) -> None:
        with self._lock:
            dead = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event_data)
                except Exception:
                    dead.append(q)
            for q in dead:
                self._subscribers.discard(q)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


_hub = StreamHub()


def get_hub() -> StreamHub:
    return _hub
