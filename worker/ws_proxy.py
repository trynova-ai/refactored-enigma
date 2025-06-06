# worker/ws_proxy.py
import asyncio, websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError

from browser_manager import BrowserManager          # ← the only import

router = APIRouter()

@router.websocket("/proxy/{session_id}")
async def proxy_session(websocket: WebSocket, session_id: str):
    await websocket.accept()                         # handshake first

    mgr = await BrowserManager.get()
    info = await mgr.get_info(session_id)            # (port, guid) or None
    print("[proxy]", session_id, "info =", info, type(info[0]))
    if info is None:
        await websocket.close(code=4404, reason="unknown session")
        return

    port, guid   = info
    chrome_ws = f"ws://127.0.0.1:{port}/devtools/browser/{guid}"

    try:
        # leave ping_interval at the default (20 s) for TCP liveness
        remote = await websockets.connect(chrome_ws, max_size=None)
    except Exception as exc:
        await websocket.close(code=1011, reason=str(exc))
        return

    # ───── forward traffic ──────────────────────────────────────────────
    async def client_to_chrome():
        try:
            async for msg in websocket.iter_text():
                await remote.send(msg)
        except WebSocketDisconnect:
            pass
        finally:
            await remote.close()

    async def chrome_to_client():
        try:
            async for msg in remote:
                await websocket.send_text(msg)
        except (ConnectionClosedOK, ConnectionClosedError):
            pass
        finally:
            await websocket.close()

    await asyncio.gather(
        client_to_chrome(),
        chrome_to_client(),
        return_exceptions=True,
    )

    # ───── clean-up ─────────────────────────────────────────────────────
    # Ensures we don’t leak a Chromium process if the client vanished.
    await mgr.close_browser(session_id)
