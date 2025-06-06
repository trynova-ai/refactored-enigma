# test_parallel_validate.py
import asyncio, sys, time, os, random
import aiohttp, redis.asyncio as aioredis, asyncpg
from playwright.async_api import async_playwright

payload = {
    "client_id": "pytest",   # anything that helps you trace the run
    "record": True           # flip ‟on” for the recorder
}

# ───────────────────────── Config ────────────────────────── #
GATEWAY   = os.getenv("GATEWAY_URL",   "http://localhost:8000")
REDIS_URL = os.getenv("REDIS_URL",     "redis://localhost:6379/0")
PG_DSN    = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/sessions",
)

# ──────────────────── Gateway helper ─────────────────────── #
async def create_session(http) -> dict:  # {"sessionId", "connectUrl"}
    r = await http.post(f"{GATEWAY}/sessions", json=payload)
    r.raise_for_status()
    return await r.json()

# ───────────────────── Job coroutine ─────────────────────── #
async def run_job(job_id: int, session_ids: list[str]):
    url = f"https://example.org/?q={random.randint(0, 9_999)}"
    async with aiohttp.ClientSession() as http:
        info = await create_session(http)
    session_ids.append(info["sessionId"])  # keep for validation

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(info["connectUrl"])
        ctx   = await browser.new_context()
        page    = await ctx.new_page()
        await page.goto(url)
        print(f"[{job_id:02}] loaded")
        # sleep 2 seconds to simulate some activity
        await asyncio.sleep(20)
        await browser.close()               # triggers gateway cleanup

# ─────────────────── Validation helpers ──────────────────── #
async def redis_assert_sessions_gone(r, ids):
    for sid in ids:
        assert not await r.hexists("session_map", sid), f"Redis leak map:{sid}"
        assert not await r.exists(f"session:{sid}"),    f"Redis leak key:{sid}"

async def pg_fetch_rows(conn, ids):
    return await conn.fetch(
        """SELECT session_id, client_id, worker_id,
                  created_at, last_active_at, ended_at, status
             FROM browser_sessions
            WHERE session_id = ANY($1::uuid[])
            ORDER BY created_at""",
        ids,
    )

async def pg_assert_rows_closed(rows):
    for r in rows:
        assert r["status"] == "closed",     f"{r['session_id']} not closed"
        assert r["ended_at"] is not None,   f"{r['session_id']} ended_at NULL"
    print(f"✔ {len(rows)} Postgres rows closed")

def print_session_stats(rows, head=5):
    durs = [(r["ended_at"] - r["created_at"]).total_seconds() for r in rows]
    print("\nSession durations (s): "
          f"min={min(durs):.2f}  avg={sum(durs)/len(durs):.2f}  max={max(durs):.2f}")

    sample = rows[:head]
    print(f"\nFirst {len(sample)} sample rows:")
    hdr = ("id", "client", "worker", "created_at", "last_active", "ended_at", "status", "dur(s)")
    print("{:36} {:7} {:15} {:26} {:26} {:26} {:8} {:>6}".format(*hdr))
    for r in sample:
        dur = (r["ended_at"] - r["created_at"]).total_seconds()
        print("{session_id} {client_id!s:7} {worker_id:15} "
              "{created_at} {last_active_at} {ended_at} {status:8} {dur:6.2f}"
              .format(dur=dur, **r))

# ────────────────────────── Main ─────────────────────────── #
async def main(n: int):
    session_ids: list[str] = []

    # 1️⃣ launch sessions in parallel
    t0 = time.perf_counter()
    await asyncio.gather(*(run_job(i, session_ids) for i in range(n)))
    total = time.perf_counter() - t0
    print(f"\nFinished {n} sessions in {total:0.2f}s "
          f"(avg {total/n:0.2f}s each)")

    # 2️⃣ allow gateway to flush state
    await asyncio.sleep(1.0)

    # 3️⃣ validate Redis + Postgres
    redis = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await redis_assert_sessions_gone(redis, session_ids)

    pg = await asyncpg.connect(PG_DSN)
    rows = await pg_fetch_rows(pg, session_ids)
    await pg_assert_rows_closed(rows)
    await pg.close()

    print_session_stats(rows)

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    asyncio.run(main(n))
