# gateway/auth/providers.py
import abc, uuid, jwt, os
from fastapi import HTTPException, status

class AuthProvider(abc.ABC):
    @abc.abstractmethod
    async def verify(self, token: str) -> uuid.UUID: ...
    async def _unauthorized(self):  # handy helper
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or missing credentials")

# ───── Clerk (first-class) ────────────────────────────────────────────
class ClerkProvider(AuthProvider):
    _pubkey = os.getenv("CLERK_JWKS_PUBLIC_KEY")   # fetch/rotate as you like

    async def verify(self, token: str) -> uuid.UUID:
        try:
            payload = jwt.decode(token, self._pubkey, algorithms=["RS256"])
            return uuid.UUID(payload["org_id"])          # or "tenant_id"
        except Exception:
            await self._unauthorized()

# ───── No-auth / local dev provider ──────────────────────────────────
class LocalProvider(AuthProvider):
    _default_tid = uuid.UUID("00000000-0000-0000-0000-000000000000")

    async def verify(self, token: str | None) -> uuid.UUID:
        # allow *any* token or none at all
        return self._default_tid
