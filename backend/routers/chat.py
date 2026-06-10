"""
Decision Router v2 — Wired to intelligent interrogation loop
Standardized API responses: {success, data, error}
"""

import uuid
import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from services.interrogation_service import interrogation_service
from services.evidence_hunter import evidence_hunter
from services.verdict_service import verdict_service
from middleware.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Emotional State Safe Mapper ─────────────────────────────────────────────

from schemas.psychology_profile import EmotionalState

EMOTIONAL_STATE_MAP = {
    "honest": EmotionalState.HONEST,
    "fear": EmotionalState.FEAR,
    "greed": EmotionalState.GREED,
    "guilt": EmotionalState.GUILT,
    "pride": EmotionalState.PRIDE,
    "desperation": EmotionalState.DESPERATION,
    "confusion": EmotionalState.CONFUSION,
    "defensive": EmotionalState.DEFENSIVE,
    "resigned": EmotionalState.RESIGNED,
    "anxious": EmotionalState.ANXIOUS,
    "avoidant": EmotionalState.AVOIDANT,
    "angry": EmotionalState.ANGRY,
    "numb": EmotionalState.NUMB,
    "evasive": EmotionalState.EVASIVE,
    "confident": EmotionalState.CONFIDENT,
    "unknown": EmotionalState.UNKNOWN,
}

# Fuzzy fallback groups
_FEAR_WORDS = {"scared", "terrified", "worried", "panicked", "afraid", "nervous"}
_ANGER_WORDS = {"frustrated", "irritated", "hostile", "resentful", "mad"}
_AVOIDANT_WORDS = {"evasive", "deflecting", "dodging", "hiding"}


def _success_response(data):
    """Return standardized success response."""
    return {"success": True, "data": data, "error": None}


def _error_response(message: str, status_code: int = 400):
    """Raise HTTPException with standardized error format."""
    raise HTTPException(
        status_code=status_code,
        detail={"success": False, "data": None, "error": message},
    )


def safe_emotional_state(raw: str) -> EmotionalState:
    """Map any LLM-returned emotional state to a valid enum, with fuzzy fallback."""
    if not raw:
        return EmotionalState.UNKNOWN
    normalized = raw.strip().lower()
    if normalized in EMOTIONAL_STATE_MAP:
        return EMOTIONAL_STATE_MAP[normalized]
    if normalized in _FEAR_WORDS:
        return EmotionalState.FEAR
    if normalized in _ANGER_WORDS:
        return EmotionalState.ANGRY
    if normalized in _AVOIDANT_WORDS:
        return EmotionalState.AVOIDANT
    return EmotionalState.UNKNOWN


# ─── Pydantic Models with Validation ─────────────────────────────────────────

class StartRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000, description="User's decision query")


class NextRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="User's response")
    history: List[Dict] = Field(..., min_length=1, description="Conversation history")
    session_id: str = Field(
        ...,
        min_length=8,
        max_length=64,
        pattern=r"^[a-fA-F0-9\-]{8,64}$",
        description="Session UUID (hex digits and hyphens)",
    )
    topic_category: Optional[str] = Field(None, max_length=100)


class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000, description="Original decision query")
    history: List[Dict] = Field(..., description="Full conversation history")
    session_id: str = Field(
        ...,
        min_length=8,
        max_length=64,
        pattern=r"^[a-fA-F0-9\-]{8,64}$",
        description="Session UUID (hex digits and hyphens)",
    )


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/start")
async def start_decision(request: StartRequest, user_usage=Depends(check_rate_limit)):
    """Initialize a new decision session."""
    try:
        query = request.query.strip()

        if not query or len(query) < 2:
            _error_response("Please describe your decision (at least 2 characters)")

        session_id = str(uuid.uuid4())
        logger.info(f"[CHAT] Starting session {session_id[:8]} for query: {query}")

        # Classify the decision
        classification = await interrogation_service.classify_decision(query)

        # REJECTION / GREETING ROUTING
        if classification.get("weight") == "ignore" or classification.get("is_decision") is False:
            logger.info(f"[CHAT] Input rejected as non-decision: {query}")
            return _success_response({
                "session_id": session_id,
                "status": "decision_complete",
                "verdict": {
                    "status": "NO-GO",
                    "confidence": 100,
                    "summary": "Interaction Rejected",
                    "the_truth": "You are procrastinating by offering pleasantries instead of problems.",
                    "rationales": ["No decision presented", "Pointless social ritual"],
                    "key_advice": ["Formulate a real dilemma", "Stop avoiding the hard work"],
                    "psychology_exposure": {
                        "stated_want": query,
                        "real_want": "Attention / Distraction",
                        "core_delusion": "That I care about 'Hi'"
                    },
                    "meta": {"is_rejection": True}
                },
                "decision_type": "not_a_decision",
                "topic_category": "greeting"
            })

        # LIGHTWEIGHT DECISION ROUTING
        if classification.get("weight") == "lightweight":
            logger.info(f"[CHAT] Lightweight decision detected: {query}")
            return _success_response({
                "session_id": session_id,
                "status": "decision_complete",
                "verdict": {
                    "decision": "GO",
                    "summary": "You're not asking because you're unsure. You're avoiding stopping.",
                    "the_truth": "It's a low-stakes choice. You already decided, you just want permission.",
                    "confidence": 80,
                    "psychology_exposure": {
                        "val": "Lightweight",
                        "stated_want": query,
                        "real_want": "Permission to waste time",
                        "hidden_fear": "None"
                    },
                    "meta": {"is_lightweight": True}
                },
                "decision_type": classification.get("decision_type"),
                "topic_category": classification.get("topic_category"),
                "is_lightweight": True,
                "meta": {"is_lightweight": True}
            })

        # Generate opening questions
        questions = await interrogation_service.generate_initial_questions(
            query=query,
            session_id=session_id,
            classification=classification,
        )

        logger.info(f"[CHAT] Started session {session_id[:8]}... with {len(questions)} questions")

        return _success_response({
            "session_id": session_id,
            "questions": questions,
            "status": "initial_phase",
            "decision_type": classification.get("decision_type"),
            "topic_category": classification.get("topic_category"),
            "min_questions": interrogation_service.MIN_QUESTIONS,
            "max_questions": interrogation_service.MAX_QUESTIONS,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[CHAT] Error in start_decision: {e}")
        _error_response(f"Internal server error: {str(e)}", 500)


@router.post("/next")
async def next_question(request: NextRequest, user_usage=Depends(check_rate_limit)):
    """Process answers and get next question (or trigger verdict)."""
    try:
        if not request.history:
            _error_response("No conversation history provided", 400)

        logger.info(f"[CHAT] Processing {len(request.history)} answers for session {request.session_id[:8]}...")

        result = await interrogation_service.process_answer_and_get_next(
            query=request.query,
            session_id=request.session_id,
            history=request.history,
            topic_category=request.topic_category,
        )

        return _success_response(result)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[CHAT] Error in next_question: {e}")
        _error_response(f"Internal server error: {str(e)}", 500)


@router.post("/analyze")
async def analyze_decision(request: AnalyzeRequest, user_usage=Depends(check_rate_limit)):
    """Generate final verdict with web research."""
    try:
        logger.info(f"[CHAT] Generating verdict for: {request.query[:50]}...")

        profile = interrogation_service.get_session_profile(request.session_id)
        search_profile = interrogation_service.get_search_profile(request.session_id)
        classification = await interrogation_service.classify_decision(request.query)

        # Hunt for evidence
        research = await evidence_hunter.hunt(
            query=request.query,
            profile=search_profile,
            classification=classification,
        )

        from schemas.psychology_profile import PsychologyProfile, DecisionType

        prof_data = profile.get("profile", {})

        psych_profile = PsychologyProfile(
            decision_type=DecisionType.PERSONAL,
            topic_category=classification.get("topic_category", "general"),
            stated_reason=prof_data.get("stated_reason") or "",
            real_motivation=prof_data.get("real_motivation"),
            hidden_fear=prof_data.get("hidden_fear"),
            core_delusion=prof_data.get("core_delusion"),
            target_person=prof_data.get("target_person"),
            core_fear=prof_data.get("core_fear"),
            competence_gap=prof_data.get("competence_gap"),
            root_insecurity=prof_data.get("root_insecurity"),
            questions_asked=len(request.history),
            exposure_confidence=int(profile.get("confidence", 0)),
            emotional_state=safe_emotional_state(prof_data.get("emotional_state", "unknown")),
            vectors_used=[],
            options=classification.get("options", []),
            nerve_hypothesis=prof_data.get("nerve_hypothesis"),
            weaponizable_phrases=prof_data.get("weaponizable_phrases", [])
        )

        verdict = verdict_service.generate(
            query=request.query,
            profile=psych_profile,
            history=request.history,
            skip_search=True,
            research_override=research
        )

        interrogation_service.cleanup_session(request.session_id)

        return _success_response(verdict)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[CHAT] Error in analyze_decision: {e}")
        _error_response(f"Internal server error: {str(e)}", 500)


@router.get("/status")
async def get_status():
    """Health check for chat router"""
    return _success_response({"status": "active", "version": "v2_intelligent"})
