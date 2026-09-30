"""Phase 3.4 — pipeline load test.

Measures what the platform actually sustains, and where the time goes. Run
before reaching for Kafka or Spark: a broker proves nothing about throughput,
and optimising before measuring is guesswork.

Drives `process_raw_event` directly at a controlled concurrency, bypassing the
scheduler so the pipeline itself is what is under test rather than the tick
interval. Reports per-stage timing so the bottleneck is identified rather than
assumed.

    python benchmarks/load_test.py --events 500 --concurrency 8
"""
from __future__ import annotations

import argparse
import asyncio
import statistics as stats
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select                          # noqa: E402

from app.db.models import Report, RawEvent, Source, SourceStatus  # noqa: E402
from app.db.session import SessionLocal, engine                # noqa: E402
from app.services.ingestion.generator import generate_tick     # noqa: E402
from app.services.pipeline import runner                       # noqa: E402

STAGE_TIMES: dict[str, list[float]] = defaultdict(list)


def instrument() -> None:
    """Wrap each stage so we can attribute time without editing the pipeline."""
    from app.services.pipeline import (
        classify as classify_mod,
        corroborate as corroborate_mod,
        credibility as credibility_mod,
        dedupe as dedupe_mod,
        embeddings as embeddings_mod,
        normalize as normalize_mod,
        reliability as reliability_mod,
    )

    def wrap_sync(module, name, label):
        original = getattr(module, name)

        def timed(*a, **kw):
            t0 = time.perf_counter()
            try:
                return original(*a, **kw)
            finally:
                STAGE_TIMES[label].append((time.perf_counter() - t0) * 1000)

        setattr(module, name, timed)

    def wrap_async(module, name, label):
        original = getattr(module, name)

        async def timed(*a, **kw):
            t0 = time.perf_counter()
            try:
                return await original(*a, **kw)
            finally:
                STAGE_TIMES[label].append((time.perf_counter() - t0) * 1000)

        setattr(module, name, timed)

    wrap_sync(normalize_mod, "normalize", "1 normalize")
    wrap_async(embeddings_mod, "embed_async", "2 embed")
    wrap_sync(classify_mod, "predict_from_vector", "4 classify")
    wrap_async(corroborate_mod, "corroborate", "5 corroborate")
    wrap_async(dedupe_mod, "find_duplicate", "6 dedupe")
    wrap_sync(reliability_mod, "compute_reliability", "7 reliability")
    wrap_sync(credibility_mod, "assess", "8 credibility")

    # `runner` imports these two by name, so it holds its own reference and a
    # patch on the defining module never reaches it. Patching `runner`'s
    # namespace is what actually instruments them — without this they were
    # silently unmeasured, and their cost hid inside the unattributed remainder.
    wrap_sync(runner, "resolve_location", "3 geocode")
    wrap_async(runner, "assign_to_event", "9 cluster")


async def seed_raw_events(count: int) -> list:
    """Write raw events without processing them, so the run measures the
    pipeline rather than generation."""
    ids = []
    async with SessionLocal() as session:
        source = (
            await session.execute(
                select(Source).where(Source.status == SourceStatus.ACTIVE).limit(1)
            )
        ).scalars().first()
        while len(ids) < count:
            for item in generate_tick(8, 12):
                if len(ids) >= count:
                    break
                raw = RawEvent(
                    source_id=source.id if source else None,
                    source_type=item.source_type,
                    external_id=f"loadtest-{len(ids)}-{item.external_id}",
                    collected_at=item.collected_at,
                    payload=item.payload | {"_loadtest": True},
                )
                session.add(raw)
                await session.flush()
                ids.append(raw.id)
        await session.commit()
    return ids


async def worker(queue: asyncio.Queue, latencies: list, errors: list) -> None:
    while True:
        raw_id = await queue.get()
        if raw_id is None:
            queue.task_done()
            return
        t0 = time.perf_counter()
        try:
            async with SessionLocal() as session:
                await runner.process_raw_event(session, raw_id)
            latencies.append((time.perf_counter() - t0) * 1000)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            queue.task_done()


async def run(events: int, concurrency: int, warmup: int = 0) -> None:
    if warmup:
        # A fresh process starts with an empty corroboration cache, so every
        # city costs a live API call. Production runs warm. Measuring both is
        # the honest way to report throughput: cold start is the floor,
        # steady state is what the platform actually sustains.
        print(f"warming corroboration cache with {warmup} events …")
        warm_ids = await seed_raw_events(warmup)
        wq: asyncio.Queue = asyncio.Queue()
        for i in warm_ids:
            wq.put_nowait(i)
        for _ in range(concurrency):
            wq.put_nowait(None)
        await asyncio.gather(
            *[worker(wq, [], []) for _ in range(concurrency)]
        )
        from app.services.pipeline.corroborate import CACHE_STATS

        total = CACHE_STATS["hits"] + CACHE_STATS["misses"]
        print(
            f"  cache now {CACHE_STATS['hits']}/{total} hits "
            f"({CACHE_STATS['hits'] / total * 100 if total else 0:.0f}%)"
        )

    print(f"seeding {events} raw events …")
    ids = await seed_raw_events(events)

    instrument()
    queue: asyncio.Queue = asyncio.Queue()
    for i in ids:
        queue.put_nowait(i)
    for _ in range(concurrency):
        queue.put_nowait(None)

    latencies: list[float] = []
    errors: list[str] = []

    print(f"processing at concurrency {concurrency} …")
    t0 = time.perf_counter()
    await asyncio.gather(*[worker(queue, latencies, errors) for _ in range(concurrency)])
    elapsed = time.perf_counter() - t0

    done = len(latencies)
    rate = done / elapsed if elapsed else 0

    def pct(xs, p):
        return sorted(xs)[min(len(xs) - 1, int(len(xs) * p))] if xs else 0.0

    print("\n" + "=" * 68)
    print("THROUGHPUT")
    print("=" * 68)
    print(f"  processed          {done} / {events}")
    print(f"  errors             {len(errors)}")
    print(f"  wall time          {elapsed:.2f}s")
    print(f"  sustained rate     {rate:.1f} reports/sec   ({rate * 60:,.0f}/min)")
    from app.services.pipeline.corroborate import CACHE_STATS as _cs

    _tot = _cs["hits"] + _cs["misses"]
    print(f"  corroboration cache {_cs['hits']}/{_tot} hits ({_cs['hits'] / _tot * 100 if _tot else 0:.0f}%)")
    print(f"  end-to-end p50     {stats.median(latencies):.1f}ms")
    print(f"  end-to-end p95     {pct(latencies, 0.95):.1f}ms")

    print("\n" + "=" * 68)
    print("WHERE THE TIME GOES  (per report)")
    print("=" * 68)
    total_stage = sum(sum(v) for v in STAGE_TIMES.values())
    measured_mean = total_stage / max(done, 1)
    print(f"  {'stage':18s}{'calls':>7s}{'mean ms':>10s}{'p95 ms':>9s}{'share':>8s}")
    for label in sorted(STAGE_TIMES):
        vals = STAGE_TIMES[label]
        share = sum(vals) / total_stage * 100 if total_stage else 0
        print(
            f"  {label:18s}{len(vals):7d}{stats.mean(vals):10.2f}"
            f"{pct(vals, 0.95):9.2f}{share:7.1f}%"
        )
    mean_e2e = stats.mean(latencies) if latencies else 0.0
    print(
        f"  {'(unattributed)':18s}{'':7s}{max(mean_e2e - measured_mean, 0):10.2f}"
        f"{'':9s}{max(mean_e2e - measured_mean, 0) / mean_e2e * 100 if mean_e2e else 0:6.1f}%"
    )

    if errors:
        print("\nfirst errors:")
        for e in errors[:3]:
            print(f"  {e}")

    print("\ncleaning up load-test rows …")
    async with SessionLocal() as session:
        loaded = (
            await session.execute(select(RawEvent.id).where(RawEvent.external_id.like("loadtest-%")))
        ).scalars().all()
        if loaded:
            await session.execute(delete(Report).where(Report.raw_event_id.in_(loaded)))
            await session.execute(delete(RawEvent).where(RawEvent.id.in_(loaded)))
            await session.commit()
        print(f"  removed {len(loaded)} raw events and their reports")
    await engine.dispose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=400)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--warmup", type=int, default=0, help="events to run first to warm caches")
    args = ap.parse_args()
    asyncio.run(run(args.events, args.concurrency, args.warmup))
