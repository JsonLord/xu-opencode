from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import json
from typing import AsyncIterator

from ..core.bus import Bus, EventInstance


router = APIRouter(tags=["Events"])


@router.get("/event")
async def subscribe_events():
    async def event_generator() -> AsyncIterator[str]:
        queue: asyncio.Queue[EventInstance] = asyncio.Queue()
        
        async def handler(event: EventInstance):
            await queue.put(event)
        
        unsubscribe = Bus.subscribe_all(handler)
        
        yield f"data: {json.dumps({'type': 'server.connected', 'payload': {}})}\n\n"
        
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps({'type': event.type, 'payload': event.payload})}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'server.heartbeat', 'payload': {}})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe()
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
