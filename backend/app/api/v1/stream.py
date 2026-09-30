"""Server-sent events for live dashboard updates.

SSE rather than WebSockets: the traffic is one-way, SSE reconnects on its own,
and it is plain HTTP, so it passes through the same auth, proxies and logging
as everything else. A WebSocket would buy bidirectionality this product has no
use for.

The client reads this with `fetch` and a ReadableStream rather than
`EventSource`, because `EventSource` cannot set an Authorization header and
the alternative — a token in the query string — puts a credential somewhere it
gets logged by every proxy in between.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.security import get_current_user
from app.db.models import User
from app.services import notify

log = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["stream"])

# Long enough not to be chatter, short enough that a dead connection is
# noticed before a user wonders why the screen stopped moving.
HEARTBEAT_SECONDS = 15


def _frame(kind: str, payload: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(payload)}\n\n"


@router.get("")
async def stream(user: User = Depends(get_current_user)) -> StreamingResponse:
    """Emits a frame whenever something changed, plus a heartbeat."""

    async def generator():
        # Tell the client what it is connected to before anything happens, so
        # a silent period reads as "quiet" rather than "broken".
        yield _frame(
            "hello",
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "heartbeat_seconds": HEARTBEAT_SECONDS,
            },
        )
        with notify.subscription() as queue:
            while True:
                try:
                    message = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    # Quiet interval. The heartbeat is what tells the client
                    # the connection is alive rather than stalled.
                    yield _frame("heartbeat", {"at": datetime.now(timezone.utc).isoformat()})
                    continue
                kind = message.pop("kind", "change")
                yield _frame(kind, message)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx buffers streaming responses by default, which turns a live
            # feed into a batch delivery.
            "X-Accel-Buffering": "no",
        },
    )
