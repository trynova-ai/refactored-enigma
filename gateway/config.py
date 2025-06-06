import os
from functools import lru_cache
from pydantic import Field

class Settings:
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/sessions")
    session_timeout: int = int(os.getenv("SESSION_TIMEOUT", "3600"))
    idle_timeout: int = int(os.getenv("IDLE_TIMEOUT", "300"))

    minio_endpoint: str = Field(..., env="MINIO_ENDPOINT")
    minio_access_key: str = Field(..., env="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(..., env="MINIO_SECRET_KEY")
    minio_bucket: str = Field("recordings", env="MINIO_BUCKET")

    # worker-availability set in Redis
    redis_workers_load_key: str = "workers_load"     # sorted-set
    redis_session_map_key: str = "session_map"       # hash: session→worker
    redis_last_active_key: str = "session_last_active"  # zset score = epoch sec

@lru_cache
def get_settings() -> Settings:
    return Settings()
