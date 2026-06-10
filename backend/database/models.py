# database/models.py
"""
SQLAlchemy models for whyLayer database.
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, ForeignKey, Date, Text
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, date, timedelta

Base = declarative_base()


class User(Base):
    """User account (or guest fingerprint)"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=True)  # From Google
    google_id = Column(String(255), unique=True, nullable=True, index=True)  # Google sub
    name = Column(String(255), nullable=True)  # From Google
    picture_url = Column(String(500), nullable=True)  # Google profile pic
    fingerprint = Column(String(255), unique=True, index=True)  # Browser fingerprint
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sessions = relationship("DecisionSession", back_populates="user")
    daily_limits = relationship("DailyUsage", back_populates="user")
    
    @property
    def is_guest(self) -> bool:
        return self.google_id is None


class DailyUsage(Base):
    """Track daily decision usage for rate limiting"""
    __tablename__ = "daily_usage"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    date = Column(Date, default=date.today, index=True)
    decisions_used = Column(Integer, default=0)
    
    user = relationship("User", back_populates="daily_limits")
    
    def can_make_decision(self, is_guest: bool) -> bool:
        """Check if user can make another decision"""
        max_allowed = 1 if is_guest else 2
        return self.decisions_used < max_allowed
    
    def increment(self):
        """Increment decision count"""
        self.decisions_used += 1


class DecisionSession(Base):
    """A single decision-making session"""
    __tablename__ = "decision_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), unique=True, index=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # Decision context
    original_query = Column(Text)
    decision_type = Column(String(20))  # binary, multi, personal
    topic_category = Column(String(50))
    
    # Psychology profile (built during interrogation)
    psychology_profile = Column(JSON, default=dict)
    
    # Conversation history
    messages = Column(JSON, default=list)  # [{role, content, timestamp}]
    
    # Final verdict
    verdict = Column(String(10), nullable=True)  # GO, NO-GO, or specific option
    verdict_data = Column(JSON, nullable=True)
    
    # Search results
    search_results = Column(JSON, nullable=True)
    
    # Metadata
    status = Column(String(20), default="active", index=True)  # active, hunting, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    questions_asked = Column(Integer, default=0)
    
    user = relationship("User", back_populates="sessions")
    
    def add_message(self, role: str, content: str):
        """Add a message to the conversation"""
        if self.messages is None:
            self.messages = []
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def get_history_for_llm(self) -> list:
        """Convert messages to LLM-friendly format"""
        history = []
        messages = self.messages or []
        
        i = 0
        while i < len(messages) - 1:
            if messages[i]["role"] == "assistant" and messages[i + 1]["role"] == "user":
                history.append({
                    "question": messages[i]["content"],
                    "answer": messages[i + 1]["content"]
                })
                i += 2
            else:
                i += 1
        
        return history


class SearchCache(Base):
    """Cache search results to reduce API calls"""
    __tablename__ = "search_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    query_hash = Column(String(64), unique=True, index=True)  # MD5 of query
    query = Column(Text)
    results = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)  # 24 hours from creation
    
    @staticmethod
    def create_expiry() -> datetime:
        return datetime.utcnow() + timedelta(hours=24)
    
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at if self.expires_at else True
