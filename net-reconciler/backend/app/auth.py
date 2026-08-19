"""
Single static bearer token auth. This is a private single-user app - no
accounts, no sessions, just a shared secret from env (spec section 5).
"""
from fastapi import Header, HTTPException, status

from app.config import APP_SECRET


async def require_auth(authorization: str = Header(default="")) -> None:
    if not APP_SECRET:
        # Local dev with no secret configured - don't lock yourself out.
        return
    expected = f"Bearer {APP_SECRET}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing token")
