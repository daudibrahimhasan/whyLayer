# schemas/verdict.py
"""
Verdict output models for final decision results.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any


class WebResearch(BaseModel):
    """Web research results from evidence hunting"""
    common_experiences: List[str] = Field(default_factory=list)
    typical_outcomes: Dict[str, List[str]] = Field(
        default_factory=lambda: {"positive": [], "negative": []}
    )
    community_advice: List[str] = Field(default_factory=list)
    warning_signs: List[str] = Field(default_factory=list)
    success_patterns: List[str] = Field(default_factory=list)
    failure_patterns: List[str] = Field(default_factory=list)
    sentiment_summary: str = "Analysis based on interrogation data"
    sources: List[Dict[str, str]] = Field(default_factory=list)  # [{title, url, snippet}]
    fact_bludgeons: List[str] = Field(default_factory=list)


class VerdictRanking(BaseModel):
    """Ranking for multi-option decisions"""
    option: str
    score: int = Field(ge=0, le=100)
    verdict: str  # GO or NO-GO
    reasoning: str = ""


class PsychologyExposure(BaseModel):
    """What Ayanokouji exposed about the user"""
    stated_want: Optional[str] = None
    real_want: Optional[str] = None
    hidden_fear: Optional[str] = None
    core_delusion: Optional[str] = None
    attack_that_worked: Optional[str] = None


class Verdict(BaseModel):
    """Final verdict for a decision"""
    status: str  # GO, NO-GO
    confidence: int = Field(ge=0, le=100)
    summary: str  # Cold, analytical sentence
    
    # Reasoning
    rationales: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    deal_breakers: List[str] = Field(default_factory=list)
    
    # Action items
    key_advice: List[str] = Field(default_factory=list)
    required_actions: List[str] = Field(default_factory=list)
    receipt: List[Dict[str, str]] = Field(default_factory=list)
    
    # Success metrics
    success_probability: str = "0%"
    
    # Psychology exposure
    psychology_exposure: Optional[PsychologyExposure] = None
    the_truth: Optional[str] = None  # Brutal truth statement
    
    # Multi-option ranking (if applicable)
    ranking: Optional[List[VerdictRanking]] = None
    
    # Web research
    web_research: WebResearch = Field(default_factory=WebResearch)
    community_sentiment: str = "Neutral"
    
    # Metadata
    meta: Dict[str, Any] = Field(default_factory=dict)
