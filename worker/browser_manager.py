"""
BrowserManager 2.0
==================

* One **Chromium process per session** (not per worker).
* Each process listens on a **unique** remote-debugging port so multiple
  browsers can run side-by-side in the same container.
* Keeps a registry  session_id → (browser, port).
* Safe under concurrency with an asyncio lock.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
from typing import Dict, Optional, Tuple

from playwright.async_api import async_playwright, Browser, BrowserContext


def _pick_free_port() -> int:
    """Ask the OS for an unused TCP port and immediately release it."""
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class BrowserManager:
    _instance: Optional["BrowserManager"] = None

    def __init__(self) -> None:
        self._pw = None                            # Playwright instance
        self._browsers: Dict[str, Tuple[Browser, int, str]] = {} # sid → (browser, port, guid)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Singleton accessor
    # ------------------------------------------------------------------ #
    @classmethod
    async def get(cls) -> "BrowserManager":
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._ensure_playwright()
        return cls._instance

    async def _ensure_playwright(self) -> None:
        if self._pw is None:
            self._pw = await async_playwright().start()
    
    async def get_info(self, session_id: str) -> tuple[int, str] | None:
        async with self._lock:
            entry = self._browsers.get(session_id)
        return (entry[1], entry[2]) if entry else None # entry = (browser, port, guid)


    # ------------------------------------------------------------------ #
    # Public API – create / close browsers
    # ------------------------------------------------------------------ #
    async def new_browser(self, session_id: str) -> Tuple[int, str]:
        """
        Launch a new Chromium process and return (debug_port, browser_guid).

        The gateway will later connect to:
            ws://<worker-host>:<port>/devtools/browser/<browser_guid>
        """
        port = _pick_free_port()

        # Launch standalone Chromium
        browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                f"--remote-debugging-port={port}",
                "--remote-debugging-address=0.0.0.0",   # expose to gateway container
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        # Grab browser GUID via /json/version
        import aiohttp, json
        async with aiohttp.ClientSession() as http:
            v = await (await http.get(f"http://localhost:{port}/json/version")).json()
            ws_url: str = v["webSocketDebuggerUrl"]          # ws://127.0.0.1:PORT/devtools/browser/<guid>
            browser_guid = ws_url.rsplit("/", 1)[-1]         # take the <guid> part

        # book-keeping
        async with self._lock:
            self._browsers[session_id] = (browser, port, browser_guid)

        return port, browser_guid

    async def close_browser(self, session_id: str) -> None:
        """Dispose of the whole browser process for a session."""
        async with self._lock:
            entry = self._browsers.pop(session_id, None)

        if entry:
            browser, *_ = entry
            await browser.close()
