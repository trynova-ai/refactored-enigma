# gateway/schema.py
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict   # << add ConfigDict

class SessionInfo(BaseModel):
    sessionId:    uuid.UUID = Field(..., alias="session_id")
    workerId:     str       = Field(..., alias="worker_id")
    createdAt:    datetime  = Field(..., alias="created_at")
    lastActiveAt: datetime  = Field(..., alias="last_active_at")
    endedAt:      datetime | None = Field(None, alias="ended_at")
    status:       str

    # --- Pydantic-v2 options ---
    model_config = ConfigDict(
        from_attributes=True,   # <-- replaces orm_mode=True
        populate_by_name=True   # keep camel⇆snake flexibility
    )

class SessionList(BaseModel):
    sessions: list[SessionInfo]
