# middleware/security.py
"""
Security middleware for whyLayer backend.
Handles:
  - CSRF protection (origin/referer check)
  - Allowed origins enforcement
  - Security response headers (CSP, HSTS, etc.)
"""

import os
import logging
from urllib.parse import urlparse

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Load allowed origins from env (comma-separated)
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
)
ALLOWED_ORIGINS: set = {o.strip().rstrip("/") for o in _raw_origins.split(",") if o.strip()}

# Methods that mutate state — must pass CSRF check
CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths that are exempt from CSRF (e.g. health check, preflight)
CSRF_EXEMPT_PATHS = {"/health", "/"}


def _extract_origin(request: Request) -> str | None:
    """Return the Origin header, falling back to the Referer domain."""
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")

    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        return f"{parsed.scheme}://{parsed.netloc}"

    return None


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    1. CSRF / Origin check — rejects cross-origin mutating requests from unknown origins.
    2. Adds security headers to every response.
    """

    async def dispatch(self, request: Request, call_next) -> Response:

        # ─── CSRF Origin Check ─────────────────────────────────────────────
        if (
            request.method in CSRF_PROTECTED_METHODS
            and request.url.path not in CSRF_EXEMPT_PATHS
        ):
            origin = _extract_origin(request)

            if origin and origin not in ALLOWED_ORIGINS:
                logger.warning(
                    f"[SECURITY] CSRF blocked — origin '{origin}' not in allowlist. "
                    f"Path: {request.url.path}"
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Forbidden: cross-origin request blocked."},
                )

        # ─── Process Request ───────────────────────────────────────────────
        response: Response = await call_next(request)

        # ─── Security Headers ──────────────────────────────────────────────
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        # HSTS — only in production (when served over HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
