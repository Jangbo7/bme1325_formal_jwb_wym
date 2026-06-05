from collections import defaultdict
from typing import Callable


class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)
        self._tap_handlers = []

    def subscribe(self, event_name: str, handler: Callable[[dict], None]) -> None:
        self._handlers[event_name].append(handler)

    def tap(self, handler: Callable[[str, dict], None]) -> None:
        self._tap_handlers.append(handler)

    def publish(self, event_name: str, payload: dict) -> None:
        for tap_handler in list(self._tap_handlers):
            tap_handler(event_name, payload)
        for handler in list(self._handlers.get(event_name, [])):
            handler(payload)
