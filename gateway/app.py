from fastapi import FastAPI, WebSocket, HTTPException, status
import asyncio
from pydantic import BaseModel

from db import create_schema                      # auto-DDL
from session_manager import (
    create_session,
    close_browser,
    start_background_tasks,
)
from cdp_proxy import proxy_cdp
from session_manager import redis

# --------------------------------------------------------------------------- #
# Lifespan hook: create tables *then* launch the idle/absolute-timeout sweeper
# --------------------------------------------------------------------------- #
async def lifespan(app: FastAPI):
    await create_schema()                                   # 1️⃣ ensure tables
    start_background_tasks(asyncio.get_running_loop())      # 2️⃣ start sweeper
    yield                                                   # 3️⃣ shutdown handled automatically


app = FastAPI(title="Browser Gateway", lifespan=lifespan)

class NewSessionReq(BaseModel):
    client_id: str | None = None
    record: bool = False                 # 🆕 default: not recording

# ---------- REST API ---------- #
@app.post("/sessions", status_code=status.HTTP_201_CREATED)
async def new_session(payload: NewSessionReq):
    try:
        info = await create_session(
            client_id=payload.client_id
        )    
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {
        "sessionId": info["session_id"],
        "connectUrl": info["connect_url"],
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    await close_browser(session_id, reason="api_delete")
    return {"status": "closed"}


# ---------- WebSocket CDP proxy ---------- #
@app.websocket("/session/{session_id}")
async def ws_proxy(websocket: WebSocket, session_id: str):
    await proxy_cdp(websocket, session_id)
