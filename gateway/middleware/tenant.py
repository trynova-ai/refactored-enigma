# gateway/middleware/tenant.py
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from auth.registry import get_provider

class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth_hdr = request.headers.get("authorization")
        token = auth_hdr.split(" ", 1)[1] if auth_hdr and " " in auth_hdr else None

        tenant_id = await get_provider().verify(token)
        if not tenant_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Missing tenant_id")

        request.state.tenant_id = tenant_id      # 👈 stash for later
        response = await call_next(request)
        return response
