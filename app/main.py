"""App assembly: lifespan (demo seeding + scheduler), middleware, error handlers, routers, static pages.

Run with:  .venv\\Scripts\\python -m uvicorn app.main:app --reload   (always ONE worker)
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.core.clock import get_clock, use_clock
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.errors import install_error_handlers
from app.core.security import dummy_hash
from app.demo import router as demo_router
from app.demo.clock import DemoClock
from app.demo.seeder import seed_demo
from app.routers import (admin, auth, health, kitchen_batches, kitchen_dashboard, kitchen_meals,
                         kitchen_prebook, kitchen_routes, kitchen_setup, me, ngo, ngo_pickups, public,
                         public_records)
from app.scheduler import loop_tick, purge_old_opt_outs

log = logging.getLogger(__name__)

# uvicorn sets up only its own loggers, so this app's INFO lines (demo seeding, scheduler start/stop)
# would be dropped. Print them in the same console, once.
_app_log = logging.getLogger("app")
if not _app_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    _app_log.addHandler(_handler)
    _app_log.setLevel(logging.INFO)

s = get_settings()
if s.demo:
    use_clock(DemoClock())


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    scheduler = None
    dummy_hash()  # make it now, so the first login with an unknown username is not slower than the rest
    if settings.demo:
        with SessionLocal() as db:
            seed_demo(db, get_clock())  # idempotent; uses today's IST date
    if settings.scheduler_enabled:
        scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
        scheduler.add_job(loop_tick, "interval", seconds=settings.tick_seconds, id="loop-tick",
                          max_instances=1, coalesce=True)  # never two ticks at once
        scheduler.add_job(purge_old_opt_outs, "cron", hour=2, minute=30, id="purge-opt-outs")
        scheduler.start()
        log.info("scheduler started (tick every %s s)", settings.tick_seconds)
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
        log.info("scheduler stopped")


app = FastAPI(title="AnnamSetu", lifespan=lifespan,
              docs_url="/docs" if s.docs else None, redoc_url=None,
              openapi_url="/openapi.json" if s.docs else None)
app.add_middleware(SessionMiddleware, secret_key=s.secret_key, session_cookie="annamsetu_session",
                   max_age=12 * 3600, same_site="lax", https_only=s.secure_cookies)  # the cookie is HttpOnly
install_error_handlers(app)

# Every API router, included before the static mount (tests reuse this tuple).
API_ROUTERS = (auth.router, me.router, health.router, public.router, public_records.router, admin.router,
               kitchen_setup.router, kitchen_meals.router, kitchen_prebook.router, kitchen_batches.router,
               kitchen_routes.router, kitchen_dashboard.router, ngo.router, ngo_pickups.router)
for r in API_ROUTERS:
    app.include_router(r)
if s.demo:
    app.include_router(demo_router.router)


class StaticPages(StaticFiles):
    """The static/ folder. A path under /api that reaches it matched no API route, so it is never a page:
    it answers 405 if the path exists with other methods (e.g. POST /api/health), otherwise 404 for every
    method. (Plain StaticFiles would answer 405 to e.g. POST /api/no-such-thing.)"""

    async def get_response(self, path, scope):
        url_path = scope["path"]
        if url_path == "/api" or url_path.startswith("/api/"):
            allowed = set()
            for route in iter_route_contexts(scope["app"].routes):  # every endpoint, routers included
                if route.methods and route.path_regex.match(url_path):
                    allowed |= route.methods
            if allowed:
                raise HTTPException(405, headers={"Allow": ", ".join(sorted(allowed))})
            raise HTTPException(404)
        return await super().get_response(path, scope)


# Last: the mount at "/" catches every path the routers didn't match (an unknown /api path gets a
# problem+json 404). html=True serves index.html for "/".
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/", StaticPages(directory=STATIC_DIR, html=True), name="static")
