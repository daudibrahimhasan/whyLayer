# routers/history.py
"""
Decision history endpoints.
View past decisions and their outcomes.
Uses JWT identity when available, falling back to fingerprint for guests.
Standardized API responses: {success, data, error}
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Optional
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import User, DecisionSession
from utils.fingerprint import get_fingerprint
from utils.jwt import get_optional_user, bearer_scheme
from fastapi.security import HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/history", tags=["history"])


# ─── Helper: standardized responses ──────────────────────────────────────────

def _success_response(data):
    return {"success": True, "data": data, "error": None}


def _error_response(message: str, status_code: int = 400):
    raise HTTPException(
        status_code=status_code,
        detail={"success": False, "data": None, "error": message},
    )


# ─── Helper: resolve user identity ───────────────────────────────────────────

def _resolve_user(
    req: Request,
    db: Session,
    credentials: Optional[HTTPAuthorizationCredentials] = None,
) -> Optional[User]:
    """
    Resolve user identity: JWT preferred, fingerprint fallback for guests.
    Returns None if no identity can be resolved.
    """
    jwt_data = get_optional_user(credentials, req)
    if jwt_data:
        user_id = int(jwt_data["sub"])
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user

    # Fallback to fingerprint (guest session)
    fp = get_fingerprint(req)
    return db.query(User).filter(User.fingerprint == fp).first()


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("")
async def get_decision_history(
    req: Request,
    limit: int = 10,
    offset: int = 0,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """
    Get user's past decisions.
    Uses JWT identity when available, falls back to fingerprint for guests.
    """
    try:
        user = _resolve_user(req, db, credentials)

        if not user:
            return _success_response({
                "decisions": [],
                "total": 0,
                "message": "No decision history found"
            })

        query = db.query(DecisionSession).filter(
            DecisionSession.user_id == user.id,
            DecisionSession.status == "completed"
        ).order_by(DecisionSession.completed_at.desc())

        total = query.count()
        decisions = query.offset(offset).limit(limit).all()

        history = []
        for d in decisions:
            history.append({
                "session_id": d.session_id,
                "query": d.original_query,
                "decision_type": d.decision_type,
                "topic": d.topic_category,
                "verdict": d.verdict,
                "confidence": d.verdict_data.get("confidence") if d.verdict_data else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "completed_at": d.completed_at.isoformat() if d.completed_at else None,
                "questions_asked": d.questions_asked,
            })

        return _success_response({
            "decisions": history,
            "total": total,
            "limit": limit,
            "offset": offset,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[HISTORY] Error in get_decision_history: {e}")
        _error_response(f"Internal server error: {str(e)}", 500)


@router.get("/{session_id}")
async def get_decision_detail(
    session_id: str,
    req: Request,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """
    Get detailed view of a past decision.
    """
    try:
        user = _resolve_user(req, db, credentials)

        if not user:
            _error_response("Decision not found", 404)

        decision = db.query(DecisionSession).filter(
            DecisionSession.session_id == session_id,
            DecisionSession.user_id == user.id
        ).first()

        if not decision:
            _error_response("Decision not found", 404)

        return _success_response({
            "session_id": decision.session_id,
            "query": decision.original_query,
            "decision_type": decision.decision_type,
            "topic": decision.topic_category,
            "status": decision.status,
            "verdict": decision.verdict,
            "verdict_data": decision.verdict_data,
            "psychology_profile": decision.psychology_profile,
            "messages": decision.messages,
            "search_results": decision.search_results,
            "questions_asked": decision.questions_asked,
            "created_at": decision.created_at.isoformat() if decision.created_at else None,
            "completed_at": decision.completed_at.isoformat() if decision.completed_at else None,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[HISTORY] Error in get_decision_detail: {e}")
        _error_response(f"Internal server error: {str(e)}", 500)


@router.delete("/{session_id}")
async def delete_decision(
    session_id: str,
    req: Request,
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """
    Delete a past decision from history.
    """
    try:
        user = _resolve_user(req, db, credentials)

        if not user:
            _error_response("Decision not found", 404)

        decision = db.query(DecisionSession).filter(
            DecisionSession.session_id == session_id,
            DecisionSession.user_id == user.id
        ).first()

        if not decision:
            _error_response("Decision not found", 404)

        db.delete(decision)
        db.commit()

        return _success_response({"message": "Decision deleted"})

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[HISTORY] Error in delete_decision: {e}")
        _error_response(f"Internal server error: {str(e)}", 500)
