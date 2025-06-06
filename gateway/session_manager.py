"""
Session bookkeeping / load-balancing (SQLAlchemy + Redis version).
Only the create / close logic changed – timeout sweeper is untouched.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Sequence

import redis.asyncio as aioredis
from aiohttp import ClientSession
from sqlalchemy import text
from ulid import ULID

from config import get_settings, Settings
from db import get_session
from models import BrowserSession

settings: Settings = get_settings()
redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)

# ───────────────────── Lua helper for worker pick ───────────────────── #

_PICK_WORKER_LUA = """
local max = tonumber(ARGV[1])
local c = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
if not c[1] then return nil end
local w, load = c[1], tonumber(c[2])
if max and load >= max then return nil end
redis.call('ZINCRBY', KEYS[1], 1, w)
return w
"""

async def pick_worker(max_contexts: int | None = None) -> str | None:
    return await redis.eval(
        _PICK_WORKER_LUA, 1,
        settings.redis_workers_load_key,
        str(max_contexts or ""),
    )

async def decrement_worker_load(w: str) -> None:
    await redis.zincrby(settings.redis_workers_load_key, -1, w)

# ────────────────────────── Public API ────────────────────────── #

async def create_session(client_id: str | None) -> dict[str, str]:
    # ULID → UUID keeps ordering benefits while matching DB column type
    public_host = os.getenv("PUBLIC_GATEWAY_HOST", "localhost")
    session_id = str(ULID().to_uuid())
    worker_host = await pick_worker()
    if not worker_host:
        raise RuntimeError("No available workers")

    # 1️⃣ ask worker to spin up a *new browser process*
    async with ClientSession() as http:
        resp = await http.post(
            f"http://{worker_host}:5000/browser",
            json={"session_id": session_id},
        )
        if resp.status != 200:
            await decrement_worker_load(worker_host)
            raise RuntimeError(f"{worker_host}: {resp.status} {await resp.text()}")
        data = await resp.json()
        browser_id: str = data["browserId"]
        port: int      = data["port"]

    # 2️⃣ persist row
    async with get_session() as db:
        db.add(BrowserSession(
            session_id=session_id,
            client_id=client_id,
            worker_id=worker_host,
        ))
        await db.commit()

    # 3️⃣ cache in Redis
    now = int(datetime.now(tz=timezone.utc).timestamp())
    pipe = redis.pipeline()
    pipe.hset(settings.redis_session_map_key, session_id, worker_host)
    pipe.hset(f"session:{session_id}", mapping={
        "browserId": browser_id,
        "port":     port,
    })
    pipe.zadd(settings.redis_last_active_key, {session_id: now})
    await pipe.execute()

    return {
        "session_id": session_id,
        "connect_url": f"ws://{public_host}:8000/session/{session_id}",
    }

async def touch_session(session_id: str) -> None:
    now = int(datetime.now(tz=timezone.utc).timestamp())
    await redis.zadd(settings.redis_last_active_key, {session_id: now})

async def close_browser(session_id: str, reason: str = "client_closed") -> None:
    worker_host = await redis.hget(settings.redis_session_map_key, session_id)
    if not worker_host:
        return

    async with ClientSession() as http:
        await http.delete(f"http://{worker_host}:5000/browser/{session_id}")
    await decrement_worker_load(worker_host)

    # Redis cleanup
    pipe = redis.pipeline()
    pipe.hdel(settings.redis_session_map_key, session_id)
    pipe.delete(f"session:{session_id}")
    pipe.zrem(settings.redis_last_active_key, session_id)
    await pipe.execute()

    # DB update
    async with get_session() as db:
        await db.execute(
            text("UPDATE browser_sessions SET ended_at = NOW(), status='closed' WHERE session_id = :sid"),
            {"sid": session_id},
        )
        await db.commit()


# --------------------------------------------------------------------------- #
# Idle / absolute timeout sweeper
# --------------------------------------------------------------------------- #

async def _timeout_sweeper() -> None:
    """Runs forever; kills sessions that exceed idle or absolute limits."""
    idle_s = settings.idle_timeout
    abs_s  = settings.session_timeout

    while True:
        now_epoch = int(datetime.now(tz=timezone.utc).timestamp())
        idle_cutoff = now_epoch - idle_s

        # -- 1. idle timeout via Redis -------------------------------------- #
        expired_idle: Sequence[str] = await redis.zrangebyscore(
            settings.redis_last_active_key, "-inf", idle_cutoff
        )

        # -- 2. absolute timeout via SQLAlchemy ----------------------------- #
        async with get_session() as db:
            rows = await db.scalars(
                text(
                    "SELECT session_id FROM browser_sessions "
                    "WHERE status='active' "
                    "AND (NOW() - created_at) > (:abs * INTERVAL '1 second')"
                ),
                {"abs": abs_s},
            )
            expired_abs = list(rows)

        # union
        for sid in set(expired_idle) | set(map(str, expired_abs)):
            try:
                await close_browser(sid, reason="timeout")
            except Exception as exc:
                # never break the loop
                print(f"[sweeper] could not close {sid}: {exc}")

        await asyncio.sleep(30)   # twice a minute


def start_background_tasks(loop: asyncio.AbstractEventLoop) -> None:
    loop.create_task(_timeout_sweeper())
