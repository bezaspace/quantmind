"""Audit middleware for FastAPI requests."""

from __future__ import annotations

import time
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..audit import get_audit_logger


class AuditMiddleware(BaseHTTPMiddleware):
    """Log every request to the audit database with timing and redaction."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        if request.url.path in ("/health", "/docs", "/openapi.json", "/favicon.ico"):
            return response

        logger = get_audit_logger()
        logger.log(
            action="api_request",
            actor=request.headers.get("X-API-Key") or "anonymous",
            session_id=request.query_params.get("session_id") or request.path_params.get("session_id"),
            payload={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        return response
