from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        for handler in self._subscribers.get(event_type, []):
            if inspect.iscoroutinefunction(handler):
                await handler(payload)
            else:
                handler(payload)
