from collections import defaultdict
from typing import Callable


class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, event_name: str, handler: Callable[[dict], None]) -> None:
        self._handlers[event_name].append(handler)

    def publish(self, event_name: str, payload: dict) -> None:
        for handler in list(self._handlers.get(event_name, [])):
            handler(payload)
