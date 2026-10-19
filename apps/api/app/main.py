"""FastAPI application for the Indian market intelligence product."""
from __future__ import annotations

import logging
import sys
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import REPO_ROOT, get_settings
from app.db import SessionLocal, init_db
from app.routers import account, auth, autotrader, market, research, upstox
from app.security import hash_password
from app.worker import start_scheduler

SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("bazaar")

_HITS: dict[str, list[float]] = defaultdict(list)


def _seed_admin() -> None:
    from sqlalchemy import select

    from app.models import User

    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        return
    db = SessionLocal()
    try:
        email = settings.admin_email.lower()
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            existing.role = "admin"
            db.commit()
            return
        db.add(
            User(
                email=email,
                password_hash=hash_password(settings.admin_password),
                name="Administrator",
                role="admin",
                plan="premium",
                email_verified=True,
            )
        )
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _seed_admin()
    from app.services.board import prime_board

    prime_board()
    scheduler = start_scheduler() if get_settings().scheduler_enabled else None
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Stoxs8", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/v1/auth"):
        key = f"{request.client.host if request.client else 'local'}:{request.url.path}"
        now = time.time()
        hits = [stamp for stamp in _HITS[key] if now - stamp < 60]
        if len(hits) >= 20:
            return JSONResponse({"detail": "Too many authentication attempts. Wait a minute."}, status_code=429)
        hits.append(now)
        _HITS[key] = hits
    return await call_next(request)


@app.get("/api/v1/health")
def health():
    return {
        "status": "ok",
        "data_mode": get_settings().data_mode,
        "live_trading_enabled": False,
        "product": "Stoxs8",
    }


app.include_router(auth.router)
app.include_router(market.router)
app.include_router(research.router)
app.include_router(account.router)
app.include_router(upstox.router)
app.include_router(autotrader.router)
