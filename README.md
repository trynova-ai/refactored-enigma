# Parallel Browsers as a Service

## What this project is

An **elastic, session-oriented remote-browser service**: the *gateway* receives API calls from clients, spins up an isolated Chromium instance on the least-loaded *worker*, and relays the Chrome DevTools Protocol (CDP) stream over a WebSocket.  
PostgreSQL records long-lived session metadata, Redis keeps fast-changing state, and MinIO stores optional video or HAR recordings.

| Component | Purpose | Ports (host) |
|-----------|---------|--------------|
| Gateway   | FastAPI REST & WS entrypoint; balances sessions | 8000 |
| Worker    | Launches one Chromium per session; CDP proxy   | none (internal) |
| Redis     | Load balancer, heart-beat, cache               | 6379 |
| Postgres  | Persistent session log                         | 5432 |
| MinIO     | S3-compatible object store for recordings      | 9000 / 9001 |

### High-level request flow

1. **Client** posts “create session” to the gateway.  
2. Gateway selects the least-loaded worker from a Redis ZSET and asks it to start a new Chromium process (one per session).  
3. Worker returns its chosen debug port plus the browser GUID; gateway stores that in Redis and Postgres.  
4. Client upgrades to WebSocket `/session/{id}`; gateway pipes every CDP frame between the client and worker.  
5. A background “sweeper” in the gateway terminates idle or long-running sessions and updates both Redis and the database.

### Bringing the stack up

All services run in Docker; no system packages are required beyond Docker Engine + Compose.  

```bash
docker compose build
docker compose up -d
```

### Running the test-suite

Unit tests target both the CDP proxy and the session machinery.  
Insert the **Test commands** snippet below in the repo root.

```bash
pytest -q test_cdp.py
pytest -q test_parallel_validate.py
pytest -q test_parallel.py
```

### Environment tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_TIMEOUT` | 3600 s | Hard cutoff per session |
| `IDLE_TIMEOUT`    |  300 s | Disconnect after inactivity |
| `MAX_CONTEXTS`    |   20   | Max concurrent Chromium per worker |
| `MINIO_BUCKET`    | recordings | Object-store bucket for assets |

Adjust these in `docker-compose.yml` as needed.

### Shutting everything down

```bash
docker compose down -v
```

