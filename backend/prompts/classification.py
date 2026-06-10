# prompts/classification.py
"""
Decision type classification prompt.
Used to analyze the first message and classify the decision type.
"""

CLASSIFICATION_PROMPT = """Classify this input. Is it a real decision that needs analysis, or just noise?

Input: "{query}"

Respond ONLY with JSON:
{{
    "is_decision": true/false,
    "decision_type": "binary|multi|personal|not_a_decision",
    "topic_category": "career|finance|relationship|purchase|health|lifestyle|education|entertainment|general|greeting",
    "weight": "lightweight|serious",
    "options": ["option1", "option2"] or [],
    "keywords": ["extracted", "keywords"],
    "emotional_hints": ["any emotional words"],
    "urgency": "low|medium|high|unknown",
    "rejection_reason": "why this isn't a decision" or null
}}

RULES:
- "hi", "hello", greetings = not_a_decision, category = greeting
- Single words without context = not_a_decision
- Vague statements without a choice = not_a_decision
- Real decisions have stakes, options, or consequences

WEIGHT RULES:
- "lightweight" = entertainment, food, minor purchases, aesthetic choices,
  easily reversible, no emotional stakes. Examples: "should I watch X",
  "should I try Y restaurant", "which color should I pick"
- "serious" = involves relationships, career, money, health, identity,
  other people's feelings, hard to reverse. Examples: "should I quit my job",
  "should I break up", "should I move cities"
"""

SENSITIVE_TOPICS = [
    "relationship",
    "marriage", 
    "divorce",
    "family",
    "mental_health",
    "health",
    "death",
    "breakup",
]

def get_min_questions_for_classification(decision_type: str, topic: str) -> int:
    """
    Get minimum questions based on decision type and topic.
    Personal/sensitive topics require more questions.
    """
    base_min = {
        "binary": 3,
        "multi": 3,
        "personal": 6,
    }.get(decision_type, 3)
    
    # Check if topic is sensitive
    topic_lower = topic.lower()
    for sensitive in SENSITIVE_TOPICS:
        if sensitive in topic_lower:
            return max(base_min, 6)
    
    return base_min
