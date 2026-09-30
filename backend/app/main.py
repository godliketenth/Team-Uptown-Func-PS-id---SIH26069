from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    admin,
    alerts,
    analytics,
    auth,
    events,
    map as map_api,
    reports,
    stream,
    verification,
)
from app.config import settings
from app.services import bus
from app.services.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bus.start_workers()
    if settings.scheduler_enabled:
        start_scheduler()
    else:
        log.warning("scheduler disabled; no synthetic ingestion will run")
    yield
    shutdown_scheduler()
    await bus.stop_workers()


app = FastAPI(
    title="National Weather Analytics Platform",
    description=(
        "Prototype ingestion-to-insight pipeline: multi-source collection, "
        "normalization, classification, weather corroboration, deduplication, "
        "reliability scoring and event clustering."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api/v1")
api.include_router(reports.router)
api.include_router(events.router)
api.include_router(map_api.router)
api.include_router(analytics.router)
api.include_router(verification.router)
api.include_router(alerts.router)
api.include_router(admin.router)
api.include_router(auth.router)
api.include_router(stream.router)
app.include_router(api)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "service": "weather-analytics-api", "version": "0.1.0"}
