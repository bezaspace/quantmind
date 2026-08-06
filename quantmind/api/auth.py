"""Authentication and authorization helpers for the API."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


def get_api_key(request: Request) -> Optional[str]:
    # Header: Authorization: Bearer <key>
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.split(" ", 1)[1]
    # Fallback to X-API-Key header
    return request.headers.get("X-API-Key") or os.getenv("QUANTMIND_API_KEY")


def require_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> str:
    from ..config import get_settings

    settings = get_settings()
    if not settings.require_auth:
        return "anonymous"

    token = None
    if credentials and credentials.scheme == "Bearer" and credentials.credentials:
        token = credentials.credentials
    if not token:
        token = request.headers.get("X-API-Key")

    expected = settings.api_key
    if not expected:
        raise HTTPException(status_code=500, detail="API authentication is required but no key is configured")
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return token or "anonymous"


OptionalAuth = Depends(get_api_key)
