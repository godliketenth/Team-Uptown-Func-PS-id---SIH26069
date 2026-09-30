"""In-process fan-out for live UI updates.

The dashboard polled every 5 seconds, which is the wrong shape for this
product twice over: an operations console should show an alert the moment it
is raised rather than up to five seconds later, and most of those requests
returned data that had not changed.

This is the notification side only. A message says *what kind of thing
changed*, never the thing itself — the client then refetches through the
normal authenticated endpoints. That keeps one copy of the authorisation
rules instead of two, and means this channel can never leak a row a viewer
was not entitled to see.

Deliberately in-process, like the rest of the bus. Several API workers would
each need their own fan-out, which is what Redis pub/sub or the Kafka topic
would be for; at one worker that is ceremony without benefit.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Iterator

log = logging.getLogger(__name__)

# Small on purpose. A client too slow to keep up with notifications is a
# client that should refetch and catch up, not one the pipeline should wait
# for. Dropping is the correct backpressure here because every message is
# "something changed" — losing one costs nothing as long as a later one
# arrives, and the polling fallback covers the case where none does.
QUEUE_MAX = 32

_subscribers: set[asyncio.Queue] = set()
_dropped = 0


def subscriber_count() -> int:
    return len(_subscribers)


def dropped_count() -> int:
    return _dropped


def publish(kind: str, **data) -> None:
    """Non-blocking. Safe to call from the pipeline's hot path."""
    global _dropped
    if not _subscribers:
        return
    message = {"kind": kind, **data}
    for queue in list(_subscribers):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            _dropped += 1


@contextlib.contextmanager
def subscription() -> Iterator[asyncio.Queue]:
    """Hands out the queue itself rather than an async generator.

    An earlier version yielded from a generator and the endpoint wrapped
    `__anext__()` in `asyncio.wait_for` to implement the heartbeat. That is a
    trap: `wait_for` *cancels* what it is waiting on, and cancelling
    `__anext__` throws CancelledError into the generator body, destroying the
    subscription on the first quiet interval. Waiting on `queue.get()`
    cancels cleanly, because there is no generator state to corrupt.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
    _subscribers.add(queue)
    log.info("live stream: subscriber joined (%s active)", len(_subscribers))
    try:
        yield queue
    finally:
        _subscribers.discard(queue)
        log.info("live stream: subscriber left (%s active)", len(_subscribers))
