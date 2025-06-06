"""
Worker service API  – one Chromium **per session**.

On start-up the worker registers **its own IP address** (or explicit env
WORKER_HOST) in the Redis load-balancer set so the gateway can reach it.
"""

from __future__ import annotations

import os
import socket

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from browser_manager import BrowserManager

from ws_proxy import router as ws_router

# ────────────────────── Redis registration helpers ────────────────────── #

REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
WORKERS_ZSET: str = os.getenv("REDIS_WORKERS_LOAD_KEY", "workers_load")

# Which host string should the gateway use to reach me?
WORKER_HOST: str = (
    os.getenv("WORKER_HOST")                # explicit override
    or socket.gethostbyname(socket.gethostname())  # my container IP
)

redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)


# ─────────────────────────── FastAPI app ─────────────────────────── #

app = FastAPI(title="Browser Worker")
app.include_router(ws_router)  

@app.on_event("startup")
async def _register_self() -> None:
    # score 0 → least loaded
    await redis.zadd(WORKERS_ZSET, {WORKER_HOST: 0}, nx=True)
    print(f"[worker] registered '{WORKER_HOST}' in Redis zset '{WORKERS_ZSET}'")


@app.on_event("shutdown")
async def _deregister_self() -> None:
    """
    Remove this host from the workers_load ZSET so the gateway
    won’t try to route new sessions here after we exit.
    """
    await redis.zrem(WORKERS_ZSET, WORKER_HOST)
    print(f"[worker] deregistered '{WORKER_HOST}' from '{WORKERS_ZSET}'")
    
# ---------- Pydantic model ---------- #
class NewCtxReq(BaseModel):
    session_id: str


# ---------- RPC endpoints ---------- #
@app.post("/browser")
async def new_browser(req: NewCtxReq):
    bm = await BrowserManager.get()
    try:
        port, browser_guid = await bm.new_browser(req.session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Return *both* port and targetId
    return {"browserId": browser_guid, "port": port}


@app.delete("/browser/{session_id}")
async def close_browser(session_id: str):
    bm = await BrowserManager.get()
    await bm.close_browser(session_id)
    return {"status": "closed"}
