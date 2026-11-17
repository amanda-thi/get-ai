import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .config import get_settings
from .ratelimit import limiter
from .routers import (
    auth,
    automation,
    dashboard,
    health,
    leads,
    notifications,
    outreach,
    reports,
    sources,
    tenders,
)

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop scheduler automation bersama siklus hidup aplikasi."""
    from .automation.scheduler import start_scheduler, stop_scheduler

    try:
        start_scheduler()
    except Exception as e:  # noqa: BLE001 - aplikasi tetap jalan walau scheduler gagal
        log.warning("gagal menyalakan scheduler automation: %s", e)
    try:
        yield
    finally:
        stop_scheduler()


def create_app() -> FastAPI:
    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    prod = s.app_env == "production"
    app = FastAPI(
        title="Green Eco AI Business Automation",
        docs_url=None if prod else "/docs",
        redoc_url=None,
        openapi_url=None if prod else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    for r in (
        health.router,
        auth.router,
        dashboard.router,
        automation.router,
        tenders.router,
        sources.router,
        leads.router,
        outreach.router,
        notifications.router,
        reports.router,
    ):
        app.include_router(r)
    return app


app = create_app()
