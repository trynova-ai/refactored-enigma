# gateway/app.py
from fastapi import FastAPI, WebSocket, status, Depends, Request
import asyncio
import uuid
from pydantic import BaseModel

from db import create_schema                      # auto-DDL
from session_manager import (
    create_session,
    close_browser,
    start_background_tasks,
)
from cdp_proxy import proxy_cdp
from session_manager import redis
from middleware.tenant import TenantMiddleware

# --------------------------------------------------------------------------- #
# Lifespan hook: create tables *then* launch the idle/absolute-timeout sweeper
# --------------------------------------------------------------------------- #
async def lifespan(app: FastAPI):
    await create_schema()                                   # 1️⃣ ensure tables
    start_background_tasks(asyncio.get_running_loop())      # 2️⃣ start sweeper
    yield                                                   # 3️⃣ shutdown handled automatically


app = FastAPI(title="Browser Gateway", lifespan=lifespan)
app.add_middleware(TenantMiddleware)

def current_tenant(request: Request) -> uuid.UUID:
    return request.state.tenant_id

class NewSessionReq(BaseModel):
    record: bool = False                 # 🆕 default: not recording

# ---------- REST API ---------- #
@app.post("/sessions", status_code=status.HTTP_201_CREATED)
async def new_session(
        payload: NewSessionReq,
        tenant_id: uuid.UUID = Depends(current_tenant)
    ):
    info = await create_session(
        tenant_id=tenant_id             
    )
    return {
        "sessionId":  info["session_id"],
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
