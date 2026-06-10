# schemas/psychology_profile.py
"""
Psychology Profile Schema - The core of Ayanokouji's interrogation engine.
Tracks user's psychological state and builds searchable profile.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class DecisionType(str, Enum):
    """Type of decision being made"""
    BINARY = "binary"           # Should I do X?
    MULTI_OPTION = "multi"      # A vs B vs C?
    PERSONAL = "personal"       # Relationships, identity, emotions


class EmotionalState(str, Enum):
    """Detected emotional state of user"""
    FEAR = "fear"               # Scared of outcome
    GREED = "greed"             # Wants more than they deserve
    GUILT = "guilt"             # Feels bad about wanting this
    PRIDE = "pride"             # Ego-driven decision
    DESPERATION = "desperation" # Backed into a corner
    CONFUSION = "confusion"     # Genuinely lost
    # Additional states the LLM may return
    HONEST = "honest"           # Genuinely open
    DEFENSIVE = "defensive"     # Protecting themselves
    RESIGNED = "resigned"       # Given up
    ANXIOUS = "anxious"         # Worried/nervous
    AVOIDANT = "avoidant"       # Dodging the topic
    ANGRY = "angry"             # Hostile/frustrated
    NUMB = "numb"               # Emotionally flat
    EVASIVE = "evasive"         # Actively avoiding
    CONFIDENT = "confident"     # Self-assured
    UNKNOWN = "unknown"         # Fallback


class AttackVector(str, Enum):
    """Psychological attack vectors for interrogation"""
    VANITY = "vanity"           # Need for external validation
    FEAR = "fear"               # Running FROM something
    COMPETENCE = "competence"   # Gap between fantasy and ability
    INSECURITY = "insecurity"   # Core inadequacy driving decision


class DetectedWeakness(BaseModel):
    """A weakness detected during interrogation"""
    vector: AttackVector
    evidence: str = ""          # Quote from user's answer
    intensity: int = Field(default=5, ge=1, le=10)  # How exposed is this weakness?


class PsychologyProfile(BaseModel):
    """
    Built progressively during interrogation.
    Used to generate targeted search queries.
    """
    
    # Core Decision Info
    decision_type: DecisionType = DecisionType.BINARY
    topic_category: str = "general"  # career, finance, relationship, purchase, health
    options: List[str] = Field(default_factory=list)  # ["quit job", "stay"] or multiple
    
    # User's Surface Story
    stated_reason: Optional[str] = None      # What they SAY they want
    stated_fear: Optional[str] = None        # What they SAY they're afraid of
    
    # Exposed Truth (Ayanokouji's findings)
    real_motivation: Optional[str] = None    # What they ACTUALLY want
    hidden_fear: Optional[str] = None        # What they're REALLY afraid of
    core_delusion: Optional[str] = None      # The lie they tell themselves
    
    # Emotional Markers
    emotional_state: EmotionalState = EmotionalState.CONFUSION
    emotional_intensity: int = Field(default=5, ge=1, le=10)
    
    # Practical Context
    financial_context: Optional[str] = None  # "broke", "stable", "wealthy"
    time_pressure: Optional[str] = None      # "urgent", "flexible", "none"
    stakeholders: List[str] = Field(default_factory=list)  # ["partner", "parents", "boss"]
    
    # Attack Vector Tracking
    target_person: Optional[str] = None      # Who are they trying to impress?
    core_fear: Optional[str] = None          # What are they running from?
    competence_gap: Optional[str] = None     # Fantasy vs reality gap
    root_insecurity: Optional[str] = None    # Core inadequacy
    
    # For Search Query Generation
    keywords: List[str] = Field(default_factory=list)
    regret_indicators: List[str] = Field(default_factory=list)
    key_phrases: List[str] = Field(default_factory=list)  # Quotable phrases from user
    
    # Interrogation Tracking
    contradictions: List[str] = Field(default_factory=list)
    evasions: List[str] = Field(default_factory=list)
    emotional_triggers: List[str] = Field(default_factory=list)
    detected_weaknesses: List[DetectedWeakness] = Field(default_factory=list)
    vectors_used: List[AttackVector] = Field(default_factory=list)
    last_attack_vector: Optional[AttackVector] = None

    # Verdict Generation Helpers
    nerve_hypothesis: Optional[str] = None     # The specific psychological nerve to hit
    weaponizable_phrases: List[str] = Field(default_factory=list) # Exact quotes to use against user
    
    # Confidence Tracking
    exposure_confidence: int = Field(default=0, ge=0, le=100)
    questions_asked: int = 0
    min_questions: int = 3                   # Based on decision_type
    max_questions: int = 9

    def is_ready_for_hunt(self) -> bool:
        """Determine if we have enough info to search."""
        return (
            self.questions_asked >= self.min_questions and
            self.exposure_confidence >= 70
        ) or self.questions_asked >= self.max_questions
    
    def get_min_questions(self) -> int:
        """Get minimum questions based on decision type and topic."""
        SENSITIVE_TOPICS = ["relationship", "marriage", "divorce", "family", "mental_health"]
        
        base_min = {
            DecisionType.BINARY: 3,
            DecisionType.MULTI_OPTION: 3,
            DecisionType.PERSONAL: 6,
        }.get(self.decision_type, 3)
        
        if self.topic_category.lower() in SENSITIVE_TOPICS:
            return max(base_min, 6)
        
        return base_min
    
    def calculate_exposure_confidence(self) -> int:
        """Calculate how much we've exposed about the user."""
        score = 0
        if self.real_motivation:
            score += 25
        if self.core_fear or self.hidden_fear:
            score += 25
        if self.root_insecurity:
            score += 25
        if self.target_person:
            score += 15
        if self.core_delusion:
            score += 10
        
        self.exposure_confidence = min(score, 100)
        return self.exposure_confidence


class QuestionContext(BaseModel):
    """Context for generating the next question"""
    question_number: int
    decision_topic: str
    decision_type: str
    
    # Built progressively
    stated_reason: Optional[str] = None
    detected_weaknesses: List[DetectedWeakness] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)
    evasions: List[str] = Field(default_factory=list)
    emotional_triggers: List[str] = Field(default_factory=list)
    
    # Attack tracking
    last_attack_vector: Optional[AttackVector] = None
    vectors_used: List[AttackVector] = Field(default_factory=list)
    
    # For using against user
    key_phrases: List[str] = Field(default_factory=list)
    target_person: Optional[str] = None
    core_fear: Optional[str] = None
    competence_gap: Optional[str] = None
    root_insecurity: Optional[str] = None
