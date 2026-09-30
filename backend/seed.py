"""Idempotent seed: source registry + demo users. Safe to re-run."""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import Source, SourceStatus, SourceType, User, UserRole
from app.db.session import SessionLocal, engine

# Poll intervals are honoured by the scheduler, so they are compressed from
# production cadence (an IMD bulletin is not really every 24s, and INSAT does
# not scan every 90s) - otherwise a two-minute demo would never show the slower
# sources contribute at all. Adjust them live from the admin Sources table.
SOURCES: list[dict] = [
    {"name": "Citizen App Reports", "source_type": SourceType.CITIZEN, "poll_interval_seconds": 8},
    {"name": "Public Social Stream", "source_type": SourceType.SOCIAL, "poll_interval_seconds": 8},
    {"name": "IMD Nowcast Bulletin", "source_type": SourceType.GOVERNMENT, "poll_interval_seconds": 24},
    {"name": "NDMA Advisory Feed", "source_type": SourceType.GOVERNMENT, "poll_interval_seconds": 40},
    {"name": "Open-Meteo Observations", "source_type": SourceType.WEATHER_API, "poll_interval_seconds": 60},
    {"name": "Regional News RSS", "source_type": SourceType.WEB_RSS, "poll_interval_seconds": 45},
    {"name": "INSAT Cloud Imagery", "source_type": SourceType.SATELLITE, "poll_interval_seconds": 90},
]

USERS: list[dict] = [
    {"email": "admin@demo.in", "password": "admin123", "role": UserRole.ADMIN, "full_name": "Ops Administrator"},
    {"email": "verifier@demo.in", "password": "verifier123", "role": UserRole.VERIFIER, "full_name": "Duty Verifier"},
    {"email": "analyst@demo.in", "password": "analyst123", "role": UserRole.ANALYST, "full_name": "Regional Analyst"},
]


async def seed() -> None:
    async with SessionLocal() as session:
        created_sources = 0
        for spec in SOURCES:
            exists = (
                await session.execute(select(Source.id).where(Source.name == spec["name"]))
            ).scalar_one_or_none()
            if exists:
                continue
            session.add(
                Source(
                    name=spec["name"],
                    source_type=spec["source_type"],
                    status=spec.get("status", SourceStatus.ACTIVE),
                    poll_interval_seconds=spec["poll_interval_seconds"],
                )
            )
            created_sources += 1

        created_users = 0
        for spec in USERS:
            exists = (
                await session.execute(select(User.id).where(User.email == spec["email"]))
            ).scalar_one_or_none()
            if exists:
                continue
            session.add(
                User(
                    email=spec["email"],
                    password_hash=hash_password(spec["password"]),
                    role=spec["role"],
                    full_name=spec["full_name"],
                )
            )
            created_users += 1

        await session.commit()
        print(f"seed complete: +{created_sources} sources, +{created_users} users")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
