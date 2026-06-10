import json
import os
from typing import Dict, List, Optional
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class UserPsychMemory(Base):
    __tablename__ = "user_psych_memory"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, index=True, unique=True)
    data_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

USER_MEMORY_DATABASE_URL = os.getenv("USER_MEMORY_DATABASE_URL", "sqlite:///user_memory.db")

# Prefer the app's DB engine if explicitly enabled and available.
# TODO: Migrate existing `user_memory.db` data into the main app DB when ready.
_app_engine = None
try:
    from database.connection import engine as _app_engine  # type: ignore
except Exception:
    _app_engine = None

USE_MAIN_DB_FOR_MEMORY = os.getenv("USE_MAIN_DB_FOR_MEMORY", "").lower() in {"1", "true", "yes"}
engine = _app_engine if (USE_MAIN_DB_FOR_MEMORY and _app_engine is not None) else create_engine(
    USER_MEMORY_DATABASE_URL, connect_args={"check_same_thread": False}
)

Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def get_user(user_id: str) -> Dict:
    """Retrieve user profile or create initial state."""
    db = SessionLocal()
    try:
        user_record = db.query(UserPsychMemory).filter_by(user_id=user_id).first()
        if user_record:
            return json.loads(user_record.data_json)
        else:
            initial_state = {
                "personality_type": "The Drifter",
                "dominant_pattern": None,
                "patterns": [],
                "decisions": [],
                "hidden_fears": [],
                "insecurities": [],
                "competence_gaps": [],
                "weaponizable_phrases": [],
                "total_sessions": 0,
                "avoided_decisions": 0,
                "last_seen": datetime.now().isoformat()
            }
            new_record = UserPsychMemory(
                user_id=user_id,
                data_json=json.dumps(initial_state)
            )
            db.add(new_record)
            db.commit()
            return initial_state
    finally:
        db.close()

def save_user(user_id: str, data: Dict):
    """Save user profile state."""
    data["last_seen"] = datetime.now().isoformat()
    db = SessionLocal()
    try:
        user_record = db.query(UserPsychMemory).filter_by(user_id=user_id).first()
        if user_record:
            user_record.data_json = json.dumps(data)
        else:
            user_record = UserPsychMemory(user_id=user_id, data_json=json.dumps(data))
            db.add(user_record)
        db.commit()
    finally:
        db.close()

def update_user_profile(user_id: str, profile, verdict):
    """Update user history and patterns after a decision."""
    user = get_user(user_id)
    user["total_sessions"] += 1
    
    # Track NO-GOs for escalation logic
    status = verdict.get("status", "NO-GO")
    if status == "GO":
        user["decisions"].append("GO")
    else:
        user["decisions"].append("NO-GO")
        user["avoided_decisions"] += 1
        
    # Aggregate psychological signals
    if getattr(profile, "hidden_fear", None):
        user["hidden_fears"].append(profile.hidden_fear)
    if getattr(profile, "root_insecurity", None):
        user["insecurities"].append(profile.root_insecurity)
    if getattr(profile, "competence_gap", None):
        user["competence_gaps"].append(profile.competence_gap)
        
    # Store weapons for future sessions
    if getattr(profile, "weaponizable_phrases", None):
        existing = set(user["weaponizable_phrases"])
        new = [p for p in profile.weaponizable_phrases if p not in existing]
        user["weaponizable_phrases"].extend(new[:2])    
    # Update dominant vector based on interrogation data
    if getattr(profile, "vectors_used", None) and len(profile.vectors_used) > 0:
        user["dominant_vector"] = profile.vectors_used[-1].value
        
    # Pattern Detection Logic
    pattern = None
    if getattr(profile, "hidden_fear", None):
        pattern = f"avoids due to fear: {profile.hidden_fear}"
    elif getattr(profile, "root_insecurity", None):
        pattern = f"ego protection: {profile.root_insecurity}"
    elif getattr(profile, "competence_gap", None):
        pattern = f"lacks ability: {profile.competence_gap}"

    if pattern:
        user["patterns"].append(pattern)
        # Update most frequent pattern
        user["dominant_pattern"] = max(
            set(user["patterns"]),
            key=user["patterns"].count
        )

    save_user(user_id, user)

def get_escalation_level(user_id: str) -> int:
    """Calculate harshness level based on repeated caution/avoidance."""
    user = get_user(user_id)
    decisions = user.get("decisions", [])

    # Escalation markers: 2 avoids = Level 2, 3+ avoids = Level 3 (Ruthless)
    avoid_count = decisions.count("NO-GO")
    if avoid_count >= 3:
        return 3
    elif avoid_count == 2:
        return 2
    return 1

def detect_repetition(user_id: str) -> Optional[str]:
    """Flag if a dominant pattern has been seen at least twice."""
    user = get_user(user_id)
    dominant = user.get("dominant_pattern")
    
    if dominant and user["patterns"].count(dominant) >= 2:
        return dominant
    return None
