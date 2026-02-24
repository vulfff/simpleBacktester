from collections import deque
from typing import Deque, Optional

from events import Event


class EventQueue:
    def __init__(self) -> None:
        self._queue: Deque[Event] = deque()

    def put(self, event: Event) -> None:
        self._queue.append(event)

    def get(self) -> Optional[Event]:
        if not self._queue:
            return None
        return self._queue.popleft()

    def empty(self) -> bool:
        return not self._queue
