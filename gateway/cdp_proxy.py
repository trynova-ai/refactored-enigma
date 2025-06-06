"""
CDP WebSocket proxy – now reads per-session debug PORT from Redis.
"""
import asyncio
import websockets
from fastapi import WebSocket, WebSocketDisconnect

from session_manager import touch_session, close_browser, redis, get_settings
settings = get_settings()

async def _open_remote_ws(worker: str, port: str, browser_guid: str):
    url = f"ws://{worker}:{port}/devtools/browser/{browser_guid}"
    return await websockets.connect(url, ping_interval=None, max_size=None)

async def proxy_cdp(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    worker = await redis.hget(settings.redis_session_map_key, session_id)
    if not worker:
        await websocket.close(code=4404)
        return

    sess_key = f"session:{session_id}"
    browser_id = await redis.hget(sess_key, "browserId")
    if not browser_id:
        await websocket.close(code=1011, reason="target missing")
        return

    try:
        remote_ws = await websockets.connect(
            f"ws://{worker}:5000/proxy/{session_id}",    # hop #2 goes to worker
            ping_interval=None, max_size=None
        )
    except Exception as e:
        await websocket.close(code=1011, reason=f"cannot connect to Chrome: {e}")
        return

    async def client_to_browser():
        try:
            async for msg in websocket.iter_text():
                await remote_ws.send(msg)
                await touch_session(session_id)
        except WebSocketDisconnect:
            pass
        finally:
            await close_browser(session_id, reason="client_disconnect")
            await remote_ws.close()

    async def browser_to_client():
        try:
            async for msg in remote_ws:
                await websocket.send_text(msg)
                await touch_session(session_id)
        except Exception:
            pass
        finally:
            await websocket.close()

    await asyncio.gather(client_to_browser(), browser_to_client(), return_exceptions=True)
