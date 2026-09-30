from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer, Interval, column, func, literal, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Alert,
    Event,
    EventStatus,
    EventType,
    Report,
    Source,
    SourceStatus,
    WarningLevel,
)
from app.services.pipeline.credibility import FLAG_LABELS, REVIEW_RISK
from app.services.pipeline.normalize import TRACKED_HASHTAGS
from app.db.session import get_session
from app.schemas.analytics import (
    CredibilityOut,
    DetectionStats,
    DistrictRisk,
    HourBucket,
    PreparednessOut,
    CredibilityRow,
    HashtagRow,
    HashtagsOut,
    StateRow,
    SummaryCounts,
    TimelineBucket,
    TimelineOut,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

OPEN_STATUSES = [EventStatus.DETECTED, EventStatus.CORROBORATING, EventStatus.NEEDS_REVIEW, EventStatus.VERIFIED]


@router.get("/summary", response_model=SummaryCounts)
async def summary(session: AsyncSession = Depends(get_session)) -> SummaryCounts:
    now = datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)

    events = (
        await session.execute(
            select(
                func.count(Event.id),
                func.count(Event.id).filter(Event.status.in_(OPEN_STATUSES)),
                func.count(Event.id).filter(Event.status == EventStatus.VERIFIED),
                func.count(Event.id).filter(Event.status == EventStatus.NEEDS_REVIEW),
                func.count(Event.id).filter(Event.status == EventStatus.REJECTED),
                func.avg(Event.evidence_score),
            )
        )
    ).one()

    reports = (
        await session.execute(
            select(
                func.count(Report.id),
                func.count(Report.id).filter(Report.observed_at >= hour_ago),
                func.count(Report.id).filter(Report.duplicate_of_report_id.is_not(None)),
            )
        )
    ).one()

    active_sources = (
        await session.execute(
            select(func.count(Source.id)).where(Source.status == SourceStatus.ACTIVE)
        )
    ).scalar() or 0

    by_type = dict(
        (k.value, int(v))
        for k, v in (
            await session.execute(select(Event.event_type, func.count()).group_by(Event.event_type))
        ).all()
    )
    by_status = dict(
        (k.value, int(v))
        for k, v in (
            await session.execute(select(Event.status, func.count()).group_by(Event.status))
        ).all()
    )
    by_severity = dict(
        (k.value, int(v))
        for k, v in (
            await session.execute(select(Event.severity, func.count()).group_by(Event.severity))
        ).all()
    )
    by_source = dict(
        (k.value, int(v))
        for k, v in (
            await session.execute(
                select(Report.source_type, func.count()).group_by(Report.source_type)
            )
        ).all()
    )

    total_reports = int(reports[0] or 0)
    duplicates = int(reports[2] or 0)
    return SummaryCounts(
        total_events=int(events[0] or 0),
        active_events=int(events[1] or 0),
        verified_events=int(events[2] or 0),
        needs_review_events=int(events[3] or 0),
        rejected_events=int(events[4] or 0),
        avg_evidence_score=round(float(events[5] or 0.0), 4),
        total_reports=total_reports,
        reports_last_hour=int(reports[1] or 0),
        duplicate_reports=duplicates,
        dedup_rate=round(duplicates / total_reports, 4) if total_reports else 0.0,
        active_sources=int(active_sources),
        events_by_type={t.value: by_type.get(t.value, 0) for t in EventType},
        events_by_status={s.value: by_status.get(s.value, 0) for s in EventStatus},
        events_by_severity=by_severity,
        reports_by_source_type=by_source,
    )


@router.get("/timeline", response_model=TimelineOut)
async def timeline(
    session: AsyncSession = Depends(get_session),
    hours: int = Query(24, ge=1, le=168),
    bucket_minutes: int = Query(60, ge=5, le=360),
    state: str | None = None,
    event_type: list[EventType] | None = Query(None),
) -> TimelineOut:
    """Reports per bucket, split by event type - drives the bottom strip chart."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    # date_bin gives evenly spaced buckets anchored at `start`. The width must
    # bind as a real interval - asyncpg rejects a string here.
    width = literal(timedelta(minutes=bucket_minutes), Interval)
    bucket = func.date_bin(width, Report.observed_at, start)

    filters = [
        Report.observed_at >= start,
        Report.duplicate_of_report_id.is_(None),
        Report.predicted_event_type.is_not(None),
    ]
    if state:
        filters.append(Report.state == state)
    if event_type:
        filters.append(Report.predicted_event_type.in_([e.value for e in event_type]))

    rows = (
        await session.execute(
            select(bucket.label("bucket"), Report.predicted_event_type, func.count())
            .where(*filters)
            .group_by("bucket", Report.predicted_event_type)
            .order_by("bucket")
        )
    ).all()

    types = [e.value for e in EventType]
    grid: dict[datetime, dict[str, int]] = {}
    steps = int((hours * 60) / bucket_minutes)
    for i in range(steps + 1):
        grid[start + timedelta(minutes=bucket_minutes * i)] = {t: 0 for t in types}

    for bucket_time, etype, count in rows:
        slot = grid.setdefault(bucket_time, {t: 0 for t in types})
        slot[etype] = int(count)

    buckets = [
        TimelineBucket(bucket=ts, counts=counts, total=sum(counts.values()))
        for ts, counts in sorted(grid.items())
    ]
    return TimelineOut(buckets=buckets, event_types=types)


@router.get("/by-state", response_model=list[StateRow])
async def by_state(
    session: AsyncSession = Depends(get_session),
    hours: int = Query(24, ge=1, le=720),
) -> list[StateRow]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    event_rows = (
        await session.execute(
            select(
                Event.state,
                func.count(Event.id),
                func.sum(Event.report_count),
                func.count(Event.id).filter(Event.status == EventStatus.VERIFIED),
                func.avg(Event.evidence_score),
            )
            .where(Event.state.is_not(None), Event.last_updated >= since)
            .group_by(Event.state)
            .order_by(func.count(Event.id).desc())
        )
    ).all()

    dominant_rows = (
        await session.execute(
            select(Event.state, Event.event_type, func.count(Event.id))
            .where(Event.state.is_not(None), Event.last_updated >= since)
            .group_by(Event.state, Event.event_type)
        )
    ).all()
    dominant: dict[str, tuple[str, int]] = {}
    for state_name, etype, count in dominant_rows:
        current = dominant.get(state_name)
        if current is None or count > current[1]:
            dominant[state_name] = (etype.value, int(count))

    return [
        StateRow(
            state=state_name,
            event_count=int(event_count or 0),
            report_count=int(report_count or 0),
            verified_count=int(verified or 0),
            avg_evidence_score=round(float(avg_ev or 0.0), 4),
            dominant_event_type=dominant.get(state_name, (None, 0))[0],
        )
        for state_name, event_count, report_count, verified, avg_ev in event_rows
    ]


@router.get("/hashtags", response_model=HashtagsOut)
async def hashtags(
    session: AsyncSession = Depends(get_session),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(25, ge=1, le=100),
    tracked_only: bool = False,
) -> HashtagsOut:
    """Which weather hashtags are carrying traffic - #IMD and the rest."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    tag = func.jsonb_array_elements_text(Report.hashtags).table_valued("value").render_derived()

    stmt = (
        select(tag.c.value, func.count(Report.id))
        .select_from(Report)
        .join(tag, true())
        .where(Report.observed_at >= since, Report.duplicate_of_report_id.is_(None))
        .group_by(tag.c.value)
        .order_by(func.count(Report.id).desc())
        .limit(limit * 2)
    )
    rows = (await session.execute(stmt)).all()

    # Dominant event type per hashtag, for colouring the chips.
    dom_stmt = (
        select(tag.c.value, Report.predicted_event_type, func.count(Report.id))
        .select_from(Report)
        .join(tag, true())
        .where(
            Report.observed_at >= since,
            Report.duplicate_of_report_id.is_(None),
            Report.predicted_event_type.is_not(None),
        )
        .group_by(tag.c.value, Report.predicted_event_type)
    )
    dominant: dict[str, tuple[str, int]] = {}
    for value, etype, count in (await session.execute(dom_stmt)).all():
        current = dominant.get(value)
        if current is None or count > current[1]:
            dominant[value] = (etype, int(count))

    tagged_total = (
        await session.execute(
            select(func.count(Report.id)).where(
                Report.observed_at >= since,
                Report.hashtags.is_not(None),
                func.jsonb_array_length(Report.hashtags) > 0,
            )
        )
    ).scalar() or 0

    out: list[HashtagRow] = []
    for value, count in rows:
        is_tracked = value in TRACKED_HASHTAGS
        if tracked_only and not is_tracked:
            continue
        out.append(
            HashtagRow(
                hashtag=value,
                report_count=int(count),
                tracked=is_tracked,
                top_event_type=dominant.get(value, (None, 0))[0],
            )
        )
        if len(out) >= limit:
            break

    return HashtagsOut(
        window_hours=hours, total_tagged_reports=int(tagged_total), rows=out
    )


@router.get("/credibility", response_model=CredibilityOut)
async def credibility(
    session: AsyncSession = Depends(get_session),
    hours: int = Query(24, ge=1, le=720),
) -> CredibilityOut:
    """Fake / misleading detection rollup: how much of the intake is suspect,
    and which signal raised each flag."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    totals = (
        await session.execute(
            select(
                func.count(Report.id),
                func.count(Report.id).filter(Report.misinformation_risk >= REVIEW_RISK),
                func.avg(Report.misinformation_risk),
            ).where(Report.observed_at >= since)
        )
    ).one()
    total, flagged, avg_risk = totals

    code = (
        func.jsonb_array_elements(Report.credibility_flags["flags"])
        .table_valued(column("value", JSONB))
        .render_derived()
    )
    # Build the expression once and reuse it: rebuilding it would emit a second
    # bind parameter, and Postgres would not recognise SELECT and GROUP BY as
    # the same expression.
    flag_code = code.c.value["code"].astext
    stmt = (
        select(flag_code, func.count(Report.id))
        .select_from(Report)
        .join(code, true())
        .where(Report.observed_at >= since, Report.credibility_flags.is_not(None))
        .group_by(flag_code)
        .order_by(func.count(Report.id).desc())
    )
    rows = (await session.execute(stmt)).all()

    return CredibilityOut(
        window_hours=hours,
        total_reports=int(total or 0),
        flagged_reports=int(flagged or 0),
        flagged_rate=round(int(flagged or 0) / int(total), 4) if total else 0.0,
        avg_risk=round(float(avg_risk or 0.0), 4),
        flags=[
            CredibilityRow(
                code=c, label=FLAG_LABELS.get(c, c), report_count=int(n)
            )
            for c, n in rows
            if c
        ],
    )


@router.get("/preparedness", response_model=PreparednessOut)
async def preparedness(
    session: AsyncSession = Depends(get_session),
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(20, ge=1, le=100),
) -> PreparednessOut:
    """The historical view a disaster-management body plans against: which
    districts are hit repeatedly, by what, and how fast we flag it.

    Honest about its own limits. Seasonal and monsoon-cycle analysis needs a
    year of data; the coverage note states the actual span rather than
    implying more.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    span = (
        await session.execute(
            select(
                func.min(Event.start_time),
                func.max(Event.start_time),
                func.count(Event.id),
            ).where(Event.start_time >= since)
        )
    ).one()
    first, last, total_events = span
    span_hours = round((last - first).total_seconds() / 3600, 1) if first and last else 0.0

    # --- per-district hazard profile ---------------------------------------
    rows = (
        await session.execute(
            select(
                Event.district,
                Event.state,
                Event.event_type,
                func.count(Event.id),
                func.avg(Event.evidence_score),
                func.count(Event.id).filter(Event.status == EventStatus.VERIFIED),
                func.count(Event.id).filter(Event.status == EventStatus.REJECTED),
            )
            .where(Event.start_time >= since, Event.district.is_not(None))
            .group_by(Event.district, Event.state, Event.event_type)
        )
    ).all()

    alert_rows = dict(
        (d, (int(n), int(r)))
        for d, n, r in (
            await session.execute(
                select(
                    Alert.district,
                    func.count(Alert.id),
                    func.count(Alert.id).filter(Alert.level == WarningLevel.RED),
                )
                .where(Alert.raised_at >= since, Alert.district.is_not(None))
                .group_by(Alert.district)
            )
        ).all()
    )

    districts: dict[str, dict] = {}
    for district, state, etype, n, avg_ev, verified, rejected in rows:
        entry = districts.setdefault(
            district,
            {
                "district": district,
                "state": state,
                "event_count": 0,
                "hazard_counts": {},
                "evidence_sum": 0.0,
                "verified": 0,
                "rejected": 0,
            },
        )
        key = etype.value if hasattr(etype, "value") else str(etype)
        entry["hazard_counts"][key] = int(n)
        entry["event_count"] += int(n)
        entry["evidence_sum"] += float(avg_ev or 0) * int(n)
        entry["verified"] += int(verified or 0)
        entry["rejected"] += int(rejected or 0)

    district_list = []
    for entry in districts.values():
        alerts, reds = alert_rows.get(entry["district"], (0, 0))
        hazards = entry["hazard_counts"]
        district_list.append(
            DistrictRisk(
                district=entry["district"],
                state=entry["state"],
                event_count=entry["event_count"],
                alert_count=alerts,
                red_alerts=reds,
                dominant_hazard=max(hazards, key=hazards.get) if hazards else None,
                hazard_counts=hazards,
                avg_evidence=round(entry["evidence_sum"] / max(entry["event_count"], 1), 4),
                verified=entry["verified"],
                rejected=entry["rejected"],
            )
        )
    # Ranked by alert burden first — that is what a planner acts on.
    district_list.sort(key=lambda d: (d.red_alerts, d.alert_count, d.event_count), reverse=True)

    hazard_totals = {
        (t.value if hasattr(t, "value") else str(t)): int(n)
        for t, n in (
            await session.execute(
                select(Event.event_type, func.count(Event.id))
                .where(Event.start_time >= since)
                .group_by(Event.event_type)
            )
        ).all()
    }

    # --- hour-of-day, in IST since that is when the reporting happens -------
    hour_expr = func.extract(
        "hour", func.timezone("Asia/Kolkata", Event.start_time)
    ).cast(Integer)
    hour_rows = (
        await session.execute(
            select(hour_expr.label("h"), Event.event_type, func.count(Event.id))
            .where(Event.start_time >= since)
            .group_by("h", Event.event_type)
        )
    ).all()
    types = [t.value for t in EventType]
    grid = {h: {t: 0 for t in types} for h in range(24)}
    for h, etype, n in hour_rows:
        key = etype.value if hasattr(etype, "value") else str(etype)
        grid[int(h)][key] = int(n)
    hour_of_day = [
        HourBucket(hour_ist=h, counts=c, total=sum(c.values())) for h, c in sorted(grid.items())
    ]

    # --- detection lead time -------------------------------------------------
    # Backfilled alerts were raised long after their event began and would
    # make this metric meaningless, so only organically-raised alerts count.
    lead = func.extract("epoch", Alert.raised_at - Event.start_time) / 60.0
    detection = (
        await session.execute(
            select(
                func.count(Alert.id),
                func.percentile_cont(0.5).within_group(lead),
                func.percentile_cont(0.9).within_group(lead),
            )
            .select_from(Alert)
            .join(Event, Event.id == Alert.event_id)
            .where(Alert.raised_at >= since, lead <= 180)
        )
    ).one()

    return PreparednessOut(
        window_days=days,
        data_span_hours=span_hours,
        coverage_note=(
            f"Based on {total_events} events spanning {span_hours:.0f} hours. "
            "Seasonal and monsoon-cycle analysis requires a year of data and is "
            "not available at this span. Hour-of-day buckets event start time, so "
            "hours when the collector was not running read as zero rather than as "
            "quiet — this is coverage, not climatology."
        ),
        districts=district_list[:limit],
        hazard_totals={t: hazard_totals.get(t, 0) for t in types},
        hour_of_day=hour_of_day,
        detection=DetectionStats(
            measured=int(detection[0] or 0),
            median_minutes=round(float(detection[1]), 1) if detection[1] is not None else None,
            p90_minutes=round(float(detection[2]), 1) if detection[2] is not None else None,
            note=(
                "Minutes from an event's first report to its first alert. "
                "Alerts raised more than 3 hours after the event began are "
                "excluded as backfill artefacts."
                # A median over one or two alerts is a single observation
                # wearing a statistic's clothing. Say so rather than let the
                # number imply a distribution that was never measured.
                + (
                    f" Only {int(detection[0])} alert(s) qualify so far — too few "
                    "for a median to mean anything yet."
                    if (detection[0] or 0) < 5
                    else ""
                )
            ),
        ),
    )
