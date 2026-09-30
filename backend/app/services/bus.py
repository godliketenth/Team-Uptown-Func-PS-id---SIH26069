"""Event bus — the transport between the collector and the pipeline workers.

Two interchangeable transports behind one façade, so no caller knows which is
in use:

  * **in-process asyncio queue** (default) — `raw_events` is the durable log
    and this queue is only the hand-off. Replay means re-reading `raw_events`,
    which is the same property a broker would give, without the ops weight.
  * **Kafka** — enabled by setting `KAFKA_BOOTSTRAP_SERVERS`. Adds durability
    of the transport itself and lets several processes share the work through
    a consumer group.

If Kafka is configured but unreachable, the bus **falls back to the in-process
queue rather than failing**, exactly as the lake falls back to local disk. A
broker that is down should degrade the platform's scale, not stop it
collecting — during a disaster the in-process path is still a working
pipeline, and an outage that silently halts ingestion is the worst possible
failure mode for this system.

Kafka is opt-in rather than the default on purpose. The load test
(`benchmarks/load_test.py`) measured 102.8 reports/sec steady-state in one
process with the time going to the outbound weather-corroboration HTTP call —
not to the queue. A broker does not make that call faster, so Kafka here buys
horizontal scale and restart-survivable backlog, not throughput.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import settings

log = logging.getLogger(__name__)

QUEUE_MAX = 5000
WORKER_COUNT = 2


@dataclass
class BusStats:
    published: int = 0
    processed: int = 0
    failed: int = 0
    last_tick_at: datetime | None = None
    last_error: str | None = None
    stage_durations_ms: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "transport": transport_name(),
            "published": self.published,
            "processed": self.processed,
            "failed": self.failed,
            # With Kafka the backlog lives in the broker, not here; the
            # scheduler refreshes `kafka_lag` and it is reported in place of a
            # queue depth that would always read zero.
            "pending": kafka_lag if _kafka_active else queue.qsize(),
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "last_error": self.last_error,
        }


queue: asyncio.Queue[uuid.UUID] = asyncio.Queue(maxsize=QUEUE_MAX)
stats = BusStats()
_workers: list[asyncio.Task] = []
kafka_lag: int | None = None

# Set at startup once the broker has actually been reached. `settings.
# kafka_enabled` says what was *asked for*; this says what is *working*.
_kafka_active = False


def transport_name() -> str:
    return "kafka" if _kafka_active else "in-process"


async def publish(raw_event_id: uuid.UUID) -> None:
    if _kafka_active:
        from app.services import kafka_bus

        try:
            await kafka_bus.publish(raw_event_id)
            stats.published += 1
            return
        except Exception as exc:
            log.error("kafka publish failed for %s (%s); using queue", raw_event_id, exc)
    await queue.put(raw_event_id)
    stats.published += 1


def publish_nowait(raw_event_id: uuid.UUID) -> bool:
    """Non-blocking publish used by the collector, which must never stall the
    scheduler tick."""
    if _kafka_active:
        # aiokafka buffers internally, so the equivalent of "don't block" is
        # to fire the send as a task. If the broker has gone away the send
        # falls back to the local queue rather than dropping the event.
        from app.services import kafka_bus

        async def _send() -> None:
            try:
                await kafka_bus.publish(raw_event_id)
            except Exception as exc:
                log.error("kafka publish failed for %s (%s); using queue", raw_event_id, exc)
                try:
                    queue.put_nowait(raw_event_id)
                except asyncio.QueueFull:
                    stats.failed += 1
                    stats.last_error = f"{type(exc).__name__}: {exc}"

        asyncio.create_task(_send())
        stats.published += 1
        return True
    try:
        queue.put_nowait(raw_event_id)
        stats.published += 1
        return True
    except asyncio.QueueFull:
        log.error("event bus full; dropping raw_event %s", raw_event_id)
        stats.failed += 1
        return False


async def _worker(worker_id: int) -> None:
    from app.db.session import SessionLocal
    from app.services.pipeline.runner import process_raw_event

    log.info("pipeline worker %s started", worker_id)
    while True:
        raw_event_id = await queue.get()
        try:
            async with SessionLocal() as session:
                await process_raw_event(session, raw_event_id)
            stats.processed += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            stats.failed += 1
            stats.last_error = f"{type(exc).__name__}: {exc}"
            log.exception("pipeline failed for raw_event %s", raw_event_id)
        finally:
            queue.task_done()


async def start_workers() -> None:
    global _kafka_active
    if settings.kafka_enabled:
        from app.services import kafka_bus

        try:
            # Connect the producer up front so an unreachable broker is a
            # startup log line, not a surprise on the first collected event.
            await kafka_bus.start_producer()
            kafka_bus.start_workers(WORKER_COUNT)
            _kafka_active = True
            log.info("bus transport: kafka (%s)", settings.kafka_bootstrap_servers)
            return
        except Exception as exc:
            log.warning(
                "kafka unreachable at %s (%s); falling back to the in-process queue",
                settings.kafka_bootstrap_servers,
                exc,
            )
    if _workers:
        return
    log.info("bus transport: in-process queue")
    for i in range(WORKER_COUNT):
        _workers.append(asyncio.create_task(_worker(i)))


async def stop_workers() -> None:
    global _kafka_active
    if _kafka_active:
        from app.services import kafka_bus

        await kafka_bus.stop_workers()
        _kafka_active = False
        return
    for task in _workers:
        task.cancel()
    for task in _workers:
        try:
            await task
        except asyncio.CancelledError:
            pass
    _workers.clear()


def mark_tick() -> None:
    stats.last_tick_at = datetime.now(timezone.utc)


async def refresh_lag() -> None:
    """Called from the scheduler tick so the admin health page shows real
    broker backlog rather than a queue depth that is structurally zero."""
    global kafka_lag
    if not _kafka_active:
        return
    from app.services import kafka_bus

    kafka_lag = await kafka_bus.lag()
