"""Seed the authority registry. Idempotent.

Contacts are illustrative placeholders — the point is the routing hierarchy,
not the address book. Webhook URLs are left empty by default so nothing is
posted to a third party without someone explicitly configuring it.
"""
import asyncio

from sqlalchemy import select

from app.db.models import Authority, AuthorityLevel, SourceStatus, WarningLevel
from app.db.session import SessionLocal, engine

AUTHORITIES: list[dict] = [
    {"name": "NDMA National Control Room", "level": AuthorityLevel.NATIONAL,
     "contact_email": "control@ndma.example.in", "min_level": WarningLevel.ORANGE},
    {"name": "IMD National Weather Desk", "level": AuthorityLevel.NATIONAL,
     "contact_email": "desk@imd.example.in", "min_level": WarningLevel.RED},

    {"name": "Maharashtra State EOC", "level": AuthorityLevel.STATE, "state": "Maharashtra",
     "contact_email": "eoc@maharashtra.example.in", "phone": "+91-22-0000000"},
    {"name": "West Bengal State EOC", "level": AuthorityLevel.STATE, "state": "West Bengal",
     "contact_email": "eoc@wb.example.in"},
    {"name": "Karnataka State EOC", "level": AuthorityLevel.STATE, "state": "Karnataka",
     "contact_email": "eoc@karnataka.example.in"},
    {"name": "Delhi State EOC", "level": AuthorityLevel.STATE, "state": "Delhi",
     "contact_email": "eoc@delhi.example.in"},
    {"name": "Bihar State EOC", "level": AuthorityLevel.STATE, "state": "Bihar",
     "contact_email": "eoc@bihar.example.in"},
    {"name": "Assam State EOC", "level": AuthorityLevel.STATE, "state": "Assam",
     "contact_email": "eoc@assam.example.in",
     "event_types": ["FLOOD", "RAIN", "THUNDERSTORM"]},
    {"name": "Gujarat State EOC", "level": AuthorityLevel.STATE, "state": "Gujarat",
     "contact_email": "eoc@gujarat.example.in"},

    {"name": "Mumbai Suburban Collectorate", "level": AuthorityLevel.DISTRICT,
     "state": "Maharashtra", "district": "Mumbai Suburban",
     "contact_email": "collector@mumbaisuburban.example.in", "phone": "+91-22-1111111"},
    {"name": "Kolkata District Control Room", "level": AuthorityLevel.DISTRICT,
     "state": "West Bengal", "district": "Kolkata",
     "contact_email": "control@kolkata.example.in"},
    {"name": "Bengaluru Urban Collectorate", "level": AuthorityLevel.DISTRICT,
     "state": "Karnataka", "district": "Bengaluru Urban",
     "contact_email": "collector@bengaluruurban.example.in"},
    {"name": "New Delhi District Control Room", "level": AuthorityLevel.DISTRICT,
     "state": "Delhi", "district": "New Delhi",
     "contact_email": "control@newdelhi.example.in"},
    {"name": "Patna District Control Room", "level": AuthorityLevel.DISTRICT,
     "state": "Bihar", "district": "Patna",
     "contact_email": "control@patna.example.in"},
    # Heat is the hazard that matters here — demonstrates per-type subscription.
    {"name": "Ahmedabad Heat Action Cell", "level": AuthorityLevel.DISTRICT,
     "state": "Gujarat", "district": "Ahmedabad",
     "contact_email": "heat@ahmedabad.example.in",
     "event_types": ["HEATWAVE", "DUST_STORM"], "min_level": WarningLevel.ORANGE},
]


async def seed() -> None:
    created = 0
    async with SessionLocal() as session:
        for spec in AUTHORITIES:
            exists = (
                await session.execute(select(Authority.id).where(Authority.name == spec["name"]))
            ).scalar_one_or_none()
            if exists:
                continue
            session.add(
                Authority(
                    name=spec["name"],
                    level=spec["level"],
                    state=spec.get("state"),
                    district=spec.get("district"),
                    contact_email=spec.get("contact_email"),
                    webhook_url=spec.get("webhook_url"),
                    phone=spec.get("phone"),
                    event_types=spec.get("event_types"),
                    min_level=spec.get("min_level", WarningLevel.ORANGE),
                    status=SourceStatus.ACTIVE,
                )
            )
            created += 1
        await session.commit()
    print(f"authority seed complete: +{created} authorities")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
