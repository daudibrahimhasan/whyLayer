# utils/jwt.py
"""
JWT token creation and validation.
Used for session authentication — replaces fingerprint-only identity.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h default

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "[SECURITY] JWT_SECRET_KEY is not set in environment variables. "
        "Generate one with: openssl rand -hex 32"
    )


def create_access_token(user_id: int, email: str, is_guest: bool = False) -> str:
    """
    Create a signed JWT access token.
    Payload includes: sub (user_id), email, is_guest, exp, iat.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=JWT_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "email": email,
        "is_guest": is_guest,
        "iat": now,
        "exp": expire,
    }

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token


def verify_access_token(token: str) -> dict:
    """
    Verify and decode a JWT token.
    Raises HTTPException 401 on any failure.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired. Please log in again.")
    except jwt.InvalidTokenError as e:
        logger.warning(f"[JWT] Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid authentication token.")


# ─── FastAPI Dependency ────────────────────────────────────────────────────────

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = None,
    req: Optional[Request] = None,
) -> dict:
    """
    Extract and validate JWT from Authorization: Bearer <token> header.
    Returns the decoded payload dict.
    Raises 401 if missing or invalid.
    """
    token = None

    # Try Authorization header
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials

    # Fallback: try cookie (for session-based flows)
    if not token and req:
        token = req.cookies.get("whyLayer_token")

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required. Please log in.")

    return verify_access_token(token)


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = None,
    req: Optional[Request] = None,
) -> Optional[dict]:
    """
    Same as get_current_user, but returns None instead of raising for unauthenticated requests.
    Useful for endpoints that support both guest and logged-in users.
    """
    try:
        return get_current_user(credentials, req)
    except HTTPException:
        return None
