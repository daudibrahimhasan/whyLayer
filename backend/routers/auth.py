# routers/auth.py
"""
Google OAuth Authentication — returns JWT tokens.
Fingerprint is stored for guest sessions but is NOT used as identity.
Identity is always validated via signed JWT.
Standardized API responses: {success, data, error}
"""

import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from database.connection import get_db
from database.models import User
from utils.jwt import create_access_token, get_current_user, bearer_scheme

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


# ─── Helper: standardized responses ──────────────────────────────────────────

def _success_response(data):
    return {"success": True, "data": data, "error": None}


def _error_response(message: str, status_code: int = 400):
    raise HTTPException(
        status_code=status_code,
        detail={"success": False, "data": None, "error": message},
    )


# ─── Request / Response Schemas ──────────────────────────────────────────────

class GoogleAuthRequest(BaseModel):
    """Google ID token sent from the frontend after Google Sign-In."""
    id_token: str = Field(..., min_length=20, max_length=10000, description="Google OAuth ID token")


class AuthResponse(BaseModel):
    """Authentication response — includes signed JWT access token."""
    success: bool
    message: str
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[dict] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/google", response_model=AuthResponse)
async def google_auth(
    payload: GoogleAuthRequest,
    db: Session = Depends(get_db),
):
    """
    Verify Google ID token -> create/update user -> return signed JWT.
    """
    try:
        if not GOOGLE_CLIENT_ID:
            _error_response("Google OAuth is not configured on the server.", 500)

        # ─── Verify Google token ───────────────────────────────────────────────
        try:
            idinfo = id_token.verify_oauth2_token(
                payload.id_token,
                google_requests.Request(),
                GOOGLE_CLIENT_ID,
                clock_skew_in_seconds=10,
            )
        except ValueError as e:
            logger.warning(f"[AUTH] Invalid Google token: {e}")
            _error_response("Invalid Google ID token.", 401)

        google_id = idinfo["sub"]
        email = idinfo.get("email", "")
        name = idinfo.get("name", "")
        picture = idinfo.get("picture", "")

        if not email or not idinfo.get("email_verified", False):
            _error_response("Google account email is not verified.", 401)

        logger.info(f"[AUTH] Google login: {email}")

        # ─── Upsert user ──────────────────────────────────────────────────────
        user = db.query(User).filter(User.google_id == google_id).first()

        if user:
            user.email = email
            user.name = name
            user.picture_url = picture
            db.commit()
            logger.info(f"[AUTH] Returning user id={user.id}")
        else:
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                picture_url=picture,
                fingerprint=None,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"[AUTH] New user created id={user.id}")

        # ─── Issue JWT ────────────────────────────────────────────────────────
        token = create_access_token(
            user_id=user.id,
            email=user.email,
            is_guest=False,
        )

        return AuthResponse(
            success=True,
            message="Login successful",
            access_token=token,
            user={
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "picture": user.picture_url,
                "is_guest": False,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[AUTH] Error in google_auth: {e}")
        _error_response(f"Internal server error: {str(e)}", 500)


@router.get("/me")
async def get_current_user_info(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    req: Request = None,
    db: Session = Depends(get_db),
):
    """
    Return current user based on JWT token — NOT fingerprint.
    Returns standardized error if no valid token present.
    """
    try:
        token_data = get_current_user(credentials, req)
        user_id = int(token_data["sub"])

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            _error_response("User not found.", 404)

        return _success_response({
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "picture": user.picture_url,
            "is_guest": user.google_id is None,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[AUTH] Error in get_current_user_info: {e}")
        _error_response(f"Internal server error: {str(e)}", 500)


@router.post("/logout")
async def logout():
    """
    Logout: client simply discards the JWT.
    Optionally set a 'whyLayer_token' cookie to empty/expired.
    """
    try:
        response = JSONResponse(content={"success": True, "data": {"message": "Logged out"}, "error": None})
        response.delete_cookie("whyLayer_token")
        return response

    except Exception as e:
        logger.exception(f"[AUTH] Error in logout: {e}")
        _error_response(f"Internal server error: {str(e)}", 500)
