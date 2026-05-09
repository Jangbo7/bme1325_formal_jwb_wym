from __future__ import annotations

import asyncio
import json
import queue

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse


router = APIRouter()


@router.get("/api/v1/events/stream")
async def stream_events(request: Request):
    bridge = request.app.state.container.get("event_bridge")
    if bridge is None:
        async def empty_stream():
            while True:
                if await request.is_disconnected():
                    break
                await asyncio.sleep(10)
                yield ": keepalive\n\n"
        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    subscriber = bridge.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    envelope = await asyncio.to_thread(subscriber.get, True, 15)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                payload = json.dumps(envelope, ensure_ascii=False)
                yield f"event: {envelope.get('event_type', 'event')}\n"
                yield f"data: {payload}\n\n"
        finally:
            bridge.unsubscribe(subscriber)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
