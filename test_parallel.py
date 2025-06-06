# test_parallel.py
import asyncio, sys, time, random, string, os, json, aiohttp
from playwright.async_api import async_playwright

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:8000")

payload = {
    "client_id": "pytest",   # anything that helps you trace the run
    "record": True           # flip ‟on” for the recorder
}

# ╭──────────────── helper ─────────────────╮
async def create_session(http) -> dict:
    r = await http.post(f"{GATEWAY}/sessions", json=payload)
    r.raise_for_status()
    return await r.json()           # {'sessionId': ..., 'connectUrl': ...}

# ╭──────────────── one job ─────────────────╮
async def run_job(job_id: int, url: str):
    async with aiohttp.ClientSession() as http:
        info = await create_session(http)
        ws   = info["connectUrl"]

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(ws)
        ctx     = await browser.new_context()
        page    = await ctx.new_page()
        await page.goto(url)
        title = await page.title()
        print(f"[{job_id:02}] {title}")
        await page.screenshot(path=f"shot-{job_id:02}.png")
        await browser.close()

# ╭──────────────── main ─────────────────╮
async def main(n: int):
    urls   = [f"https://example.org/?q={i}" for i in range(n)]
    start  = time.perf_counter()
    await asyncio.gather(*(run_job(i, u) for i, u in enumerate(urls)))
    elapsed = time.perf_counter() - start
    print(f"\nFinished {n} sessions in {elapsed:0.2f}s "
          f"(avg {elapsed/n:0.2f}s each → shows parallelism)")

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    asyncio.run(main(n))
