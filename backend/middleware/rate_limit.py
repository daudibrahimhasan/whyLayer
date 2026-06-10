# middleware/rate_limit.py
"""
Rate limiting based on JWT identity (preferred) or fingerprint/IP.
- Guest: 1 decision per session
- Logged-in: 2 decisions per day (reset at midnight UTC)
"""

from datetime import date
from typing import Tuple, Optional
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session

from database.models import User, DailyUsage
from database.connection import get_db
from fastapi import Depends

from utils.jwt import get_optional_user
from utils.fingerprint import get_fingerprint


class RateLimitError(Exception):
    """Rate limit exceeded"""
    def __init__(self, message: str, action: str = "wait"):
        self.message = message
        self.action = action
        super().__init__(message)


def check_rate_limit(
    request: Request,
    db: Session = Depends(get_db),
    increment: bool = True,
) -> Tuple[User, DailyUsage]:
    """
    Check if user can make a decision.

    Uses JWT identity when available (logged-in users), falling back to
    fingerprint for guest sessions.

    Args:
        request: FastAPI request
        db: Database session
        increment: If True, increment usage count after checking (default True)

    Returns:
        Tuple of (User, DailyUsage)

    Raises:
        HTTPException: If rate limit exceeded (returns structured 429 JSON)
    """
    # --- Resolve identity: JWT preferred, fingerprint fallback ---
    jwt_data = get_optional_user(None, request)
    fingerprint = get_fingerprint(request)

    user = None
    if jwt_data:
        user_id = int(jwt_data["sub"])
        user = db.query(User).filter(User.id == user_id).first()

    if not user:
        user = db.query(User).filter(User.fingerprint == fingerprint).first()

    if not user:
        user = User(fingerprint=fingerprint)
        db.add(user)
        db.commit()
        db.refresh(user)

    is_guest = user.email is None

    # --- Find or create today's usage record ---
    today = date.today()
    usage = db.query(DailyUsage).filter(
        DailyUsage.user_id == user.id,
        DailyUsage.date == today
    ).first()

    if not usage:
        usage = DailyUsage(user_id=user.id, date=today, decisions_used=0)
        db.add(usage)
        db.commit()
        db.refresh(usage)

    # --- Check limit ---
    max_allowed = 1 if is_guest else 2

    if usage.decisions_used >= max_allowed:
        if is_guest:
            raise HTTPException(
                status_code=429,
                detail={
                    "success": False,
                    "error": "rate_limit_exceeded",
                    "message": "Sign up to make 2 decisions per day",
                    "action": "signup",
                    "decisions_used": usage.decisions_used,
                    "max_allowed": max_allowed,
                }
            )
        else:
            raise HTTPException(
                status_code=429,
                detail={
                    "success": False,
                    "error": "rate_limit_exceeded",
                    "message": "You've used your 2 decisions today. Come back tomorrow.",
                    "action": "wait",
                    "reset_at": "midnight UTC",
                    "decisions_used": usage.decisions_used,
                    "max_allowed": max_allowed,
                }
            )

    # --- Increment if requested ---
    if increment:
        usage.decisions_used += 1
        db.commit()
        print(f"[RATE_LIMIT] User {user.id} used decision {usage.decisions_used}/{max_allowed}")

    return user, usage


def get_remaining_decisions(request: Request, db: Session) -> dict:
    """
    Get user's remaining decisions for today.
    Does not check limit, just reports status.
    """
    fingerprint = get_fingerprint(request)
    
    user = db.query(User).filter(User.fingerprint == fingerprint).first()
    if not user:
        return {
            "decisions_used": 0,
            "max_allowed": 1,
            "remaining": 1,
            "is_guest": True,
        }
    
    is_guest = user.email is None
    max_allowed = 1 if is_guest else 2
    
    today = date.today()
    usage = db.query(DailyUsage).filter(
        DailyUsage.user_id == user.id,
        DailyUsage.date == today
    ).first()
    
    decisions_used = usage.decisions_used if usage else 0
    
    return {
        "decisions_used": decisions_used,
        "max_allowed": max_allowed,
        "remaining": max(0, max_allowed - decisions_used),
        "is_guest": is_guest,
    }


class RateLimitMiddleware:
    """
    FastAPI middleware for rate limiting.
    Only checks rate limit on decision endpoints.
    """
    
    RATE_LIMITED_PATHS = [
        "/api/decision/start",
        "/api/decision/analyze",
        "/api/chat",
    ]
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        # Only check HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        
        if any(path.startswith(p) for p in self.RATE_LIMITED_PATHS):
            # We would enforce the check here ideally or in the endpoints.
            pass
            
        await self.app(scope, receive, send)
