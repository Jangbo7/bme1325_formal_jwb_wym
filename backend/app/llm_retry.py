from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")

DEFAULT_LLM_RETRIES = 2


def call_with_llm_retries(
    func: Callable[[], T],
    *,
    retries: int = DEFAULT_LLM_RETRIES,
) -> T:
    last_exc: Exception | None = None
    for attempt in range(max(0, int(retries)) + 1):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt >= max(0, int(retries)):
                raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("llm retry helper reached unreachable state")
