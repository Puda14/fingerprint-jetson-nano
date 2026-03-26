"""
Request timing middleware.
Adds an ``X-Process-Time`` header (in seconds) to every HTTP response.
"""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class ProfilingMiddleware(BaseHTTPMiddleware):
    """Measure wall-clock time for each request and attach it as a header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{elapsed:.6f}"
        return response
