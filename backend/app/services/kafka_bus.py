"""Kafka transport for the raw-event stream.

Same contract as the in-process bus: a raw event id goes in, a pipeline worker
picks it up. What Kafka adds is *durability of the transport itself* — the
in-process queue loses its backlog when the process dies, whereas a committed
Kafka offset survives a restart and a second consumer in the same group picks
up the partitions.

That matters for horizontal scale, not for throughput. The load test measured
the bottleneck as the outbound weather-corroboration HTTP call, so moving the
transport to Kafka does not make a single process faster — it makes *more than
one process* possible. Which is why this is opt-in behind
`KAFKA_BOOTSTRAP_SERVERS` and the in-process queue stays the default.

Offsets are committed only after `process_raw_event` returns, so a crash
mid-pipeline redelivers rather than silently drops. The pipeline is keyed on
`raw_event_id` and is idempotent, so redelivery is safe.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from app.config import settings

log = logging.getLogger(__name__)

CONSUMER_GROUP = "nwap-pipeline"

_producer = None
_consumers: list = []
_tasks: list[asyncio.Task] = []


async def start_producer() -> None:
    global _producer
    if _producer is not None:
        return
    from aiokafka import AIOKafkaProducer

    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        # The durable record is already in `raw_events`; acks=1 is the right
        # trade here because a lost transport message costs a reprocess, not
        # the data itself.
        acks=1,
        linger_ms=5,
    )
    await _producer.start()
    log.info("kafka producer connected to %s", settings.kafka_bootstrap_servers)


async def publish(raw_event_id: uuid.UUID) -> None:
    if _producer is None:
        await start_producer()
    # Partition by id so the same raw event always lands on one partition and
    # is therefore never processed concurrently by two workers.
    key = str(raw_event_id).encode()
    await _producer.send_and_wait(settings.kafka_topic, value=key, key=key)


async def _consume(worker_id: int) -> None:
    from aiokafka import AIOKafkaConsumer

    from app.db.session import SessionLocal
    from app.services import bus
    from app.services.pipeline.runner import process_raw_event

    consumer = AIOKafkaConsumer(
        settings.kafka_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=CONSUMER_GROUP,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    _consumers.append(consumer)
    log.info("kafka pipeline worker %s joined group %s", worker_id, CONSUMER_GROUP)
    try:
        async for msg in consumer:
            raw_event_id = uuid.UUID(msg.value.decode())
            try:
                async with SessionLocal() as session:
                    await process_raw_event(session, raw_event_id)
                bus.stats.processed += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                bus.stats.failed += 1
                bus.stats.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("pipeline failed for raw_event %s", raw_event_id)
            # Commit either way: a poison message must not block the partition
            # forever. The failure is already counted and logged, and the row
            # stays in `raw_events` for replay.
            await consumer.commit()
    finally:
        await consumer.stop()


def start_workers(count: int) -> None:
    if _tasks:
        return
    for i in range(count):
        _tasks.append(asyncio.create_task(_consume(i)))


async def stop_workers() -> None:
    for task in _tasks:
        task.cancel()
    for task in _tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    _tasks.clear()
    _consumers.clear()
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


async def lag() -> int | None:
    """Consumer-group lag across the assigned partitions — the Kafka
    equivalent of the in-process queue depth.

    Measured against the *committed* offset, not the fetch position, so this
    matches what `kafka-consumer-groups --describe` reports. The fetch
    position runs ahead of the commit by whatever is currently in the
    pipeline, which would under-report the real backlog.
    """
    if not _consumers:
        return None
    total = 0
    try:
        for consumer in _consumers:
            partitions = consumer.assignment()
            if not partitions:
                continue
            end_offsets = await consumer.end_offsets(list(partitions))
            for tp in partitions:
                committed = await consumer.committed(tp)
                if committed is None:
                    continue
                total += max(0, end_offsets.get(tp, committed) - committed)
    except Exception as exc:
        log.debug("kafka lag unavailable: %s", exc)
        return None
    return total
