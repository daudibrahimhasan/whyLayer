"""
Interrogation Prompts v4.1 — Psychological Warfare + Vector Enforcement
Every question is an attack disguised as a decision question.
The LLM is now FORCED to use the correct attack vector.
"""

from typing import List, Dict, Optional
from prompts.ayanokouji_base import PersonaConfig, AYANOKOUJI_METHOD

PHASES = {
    "extraction": {
        "goal": "Reveal what they want and what they are avoiding. No aggression yet.",
    },
    "transition": {
        "goal": "First uncomfortable observation. Pressure starts here.",
    },
    "attack": {
        "goal": "Use their own words, contradictions, and fear against them. No softness.",
    },
}


def get_phase(questions_asked: int, confidence: int, consecutive_evasions: int = 0) -> str:
    if questions_asked <= 1:
        return "extraction"
    if questions_asked == 2:
        return "transition"
    return "attack"


# ─── Vector Definitions (THE MISSING PIECE) ──────────────────────────────────
# This is WHY the LLM kept ignoring your vector selection.
# It knew the label but not what the label MEANS.

VECTOR_DEFINITIONS = {
    "vanity_attack": {
        "description": (
            "THE READ: Look for concern with perception, 'what people think', or validation. "
            "THE MOVE: Expose that they don't want the thing itself—they want the status of having it. "
            "Use an observation: 'You keep mentioning other people.' "
            "Isolate them from the audience."
        ),
        "never_ask": [
            "Don't ask about fears—that's fear territory",
            "Don't ask about logistics—that's competence territory",
        ],
    },
    "fear_attack": {
        "description": (
            "THE READ: Look for hesitation, 'still thinking', or endless research. "
            "THE MOVE: Call out the avoidance. Name the fear they refuse to name. "
            "Use an observation: 'You're not planning. You're hiding.' "
            "Make the cost of inaction tangible."
        ),
        "never_ask": [
            "Don't ask about audience—that's vanity territory",
            "Don't ask for plans—that's competence territory",
        ],
    },
    "competence_attack": {
        "description": (
            "THE READ: Look for vague words like 'figure it out', 'hustle', or 'manage'. "
            "THE MOVE: Demand the boring details they skipped. Expose the gap between fantasy and reality. "
            "Use an observation: 'You have a vision. You don't have a plan.'"
        ),
        "never_ask": [
            "Don't ask about self-worth—that's insecurity territory",
            "Don't ask about approval—that's vanity territory",
        ],
    },
    "insecurity_attack": {
        "description": (
            "THE READ: Look for qualifiers ('I think', 'maybe'), asking for permission, or self-doubt. "
            "THE MOVE: Split them in two. The one who wants it vs. the one who doesn't believe they deserve it. "
            "Use an observation: 'You don't talk like someone who believes in this.'"
        ),
        "never_ask": [
            "Don't ask about logistics—that's competence territory",
            "Don't ask about audience—that's vanity territory",
        ],
    },
}

# ─── Banned Patterns ─────────────────────────────────────────────────────────
# The LLM defaults to these lazy patterns. Block them explicitly.

BANNED_PATTERNS = [
    "what's the difference between",
    "what's the real difference between",
    "what is the difference between",
    "how is that different from",
    "what changed between",
    "what's the distinction between",
    "can you explain the difference",
]


# ─── Initial Questions Prompt ────────────────────────────────────────────────

INITIAL_QUESTIONS_PROMPT = f"""{PersonaConfig.CORE_IDENTITY}

{PersonaConfig.THREE_LAYERS}
{AYANOKOUJI_METHOD}
{PersonaConfig.SPEAKING_RULES}

A subject has come to you:
"{{query}}"

Decision type: {{decision_type}}
Category: {{topic_category}}

Generate exactly 3 opening lines.

Q1 — Extraction
- precise observation tied to the user's exact situation
- no accusation yet
- should make them reveal what they want

Q2 — Extraction
- focused question that reveals fear, priority, or desired outcome
- answerable, but revealing
- no aggression yet

Q3 — Transition
- first uncomfortable observation
- interpret their behavior
- pressure begins here
- do NOT fully attack yet

Rules:
- every line must be specific to THIS decision
- no generic filler
- no repeated angle
- max 15 words
- if the line works for another random decision, reject it
- do not use "why now", "what changed", "how do you feel", "what do you want"
- Q1 and Q3 should usually be observations
- Q2 should usually be a question

Return ONLY valid JSON:
{{{{
  "questions": [
    {{{{"text": "...", "type": "observation", "purpose": "extraction"}}}},
    {{{{"text": "...", "type": "question", "purpose": "extraction"}}}},
    {{{{"text": "...", "type": "observation", "purpose": "transition"}}}}
  ],
  "initial_read": "one-sentence hypothesis"
}}}}
"""

def get_interrogation_system_prompt() -> str:
    """
    Returns the static system prompt for the Ayanokouji persona.
    This should be sent as the 'system' role message and can be cached.
    """
    return f"""{PersonaConfig.CORE_IDENTITY}

{PersonaConfig.INTERROGATION_RULES}

{PersonaConfig.ESCALATION_RULES}"""


# ─── User Prompt (Dynamic Context) ────────────────────────────────────────────

def build_next_question_prompt(
    query: str,
    history: List[Dict],
    profile_snapshot: Dict,
    phase: str,
    phase_description: str,
    confidence: int,
    questions_asked: int,
    max_questions: int,
    required_vector: str,
    question_history: List[str],
    probe_suggestion: Optional[str] = None,
    initial_hypothesis: Optional[str] = None,
    tone_instruction: str = "",          # FIX 7: Adaptive tone per user
    grounding_instruction: str = "",     # FIX 1: Grounding mode override
) -> str:
    """Build the dynamic user context prompt (Behavioral Reading)."""

    # ─── Get vector definition ────────────────────────────────────
    vector_info = VECTOR_DEFINITIONS[required_vector]
    vector_desc = vector_info["description"]

    vector_donts = "\n".join(
        f'    x {rule}' for rule in vector_info["never_ask"]
    )

    # ─── Format conversation ──────────────────────────────────────
    formatted_history = format_history(history)

    # ─── Format previous questions for dedup ──────────────────────
    if question_history:
        prev_questions = "\n".join(
            f'    • "{q}"' for q in question_history
        )
    else:
        prev_questions = "    (none yet)"

    # ─── Format banned patterns ───────────────────────────────────
    banned_str = "\n".join(f'    x "{p}"' for p in BANNED_PATTERNS)

    # ─── Extract profile data ─────────────────────────────────────
    weapons = profile_snapshot.get("weaponizable_phrases", [])
    weapons_str = (
        "\n".join(f'    → "{w}"' for w in weapons[-5:])
        if weapons
        else "    (none extracted yet)"
    )

    nerve = profile_snapshot.get("nerve_hypothesis", "not yet identified")
    
    contradictions = profile_snapshot.get("contradictions", [])
    contradictions_str = (
        "\n".join(f'    ! {c}' for c in contradictions[-3:])
        if contradictions
        else "    (none found yet)"
    )

    current_layer = profile_snapshot.get("current_layer", "script")
    emotional_state = profile_snapshot.get("emotional_state", "unknown")
    weakness_summary = profile_snapshot.get("weakness_summary", [])
    weakness_summary_str = (
        "\n".join(f"    - {line}" for line in weakness_summary)
        if weakness_summary
        else "    - No stable read yet."
    )
    internal_deductions = profile_snapshot.get("internal_deductions", [])
    internal_deductions_str = (
        "\n".join(f"    - {line}" for line in internal_deductions[-3:])
        if internal_deductions
        else "    - No private deduction yet."
    )

    # FIX 6: Memory context from user profile (past sessions)
    memory_context = profile_snapshot.get("memory_context", {})
    memory_str = ""
    if memory_context:
        memory_lines = []
        if memory_context.get("dominant_pattern"):
            memory_lines.append(f"    PAST PATTERN: User avoids decisions due to: {memory_context['dominant_pattern']}")
        if memory_context.get("past_fears"):
            memory_lines.append(f"    PAST FEARS: {', '.join(memory_context['past_fears'])}")
        if memory_context.get("total_sessions"):
            memory_lines.append(f"    Sessions: {memory_context['total_sessions']} previous visits")
        if memory_lines:
            memory_str = "\nUSER HISTORY (from past sessions):\n" + "\n".join(memory_lines)
            memory_str += "\n    → If current behavior matches past pattern, CALL IT OUT DIRECTLY."

    # FIX 9: Mid-session insight
    insight_str = ""
    mid_insight = profile_snapshot.get("mid_session_insight")
    if mid_insight:
        insight_str = f"\nYOUR CURRENT READ (shared with user): {mid_insight}"
        insight_str += "\n    → Your next question should BUILD on this insight, not repeat it."


    # ─── Probe suggestion ─────────────────────────────────────────
    probe_line = ""
    if probe_suggestion:
        probe_line = f"\nANALYZER SUGGESTS: {probe_suggestion}"

    phase_rules = ""

    if phase == "extraction":
        phase_rules = """
PHASE: EXTRACTION
- understand, do not attack
- no accusations
- no “coward”, “hiding”, “terrified”
- reveal want / fear / desired outcome
"""
    elif phase == "transition":
        phase_rules = """
PHASE: TRANSITION
- mild interpretation
- first uncomfortable read
- pressure begins
- no full dismantling yet
"""
    elif phase == "attack":
        phase_rules = """
PHASE: ATTACK
- use their own words
- expose contradictions
- call out evasion directly
- no soft questions
- every line must corner them
"""

    return f"""===================================================
SUBJECT'S DECISION: "{query}"

CONVERSATION SO FAR:
{formatted_history}
===================================================

CURRENT READ ON SUBJECT:
    Layer: {current_layer}
    Emotional state: {emotional_state}
    Nerve hypothesis: {nerve}
    CURRENT HYPOTHESIS: {initial_hypothesis or 'unknown'}

USER WEAKNESS PROFILE:
{weakness_summary_str}

PRIVATE CASE NOTES:
{internal_deductions_str}

CONTRADICTIONS FOUND:
{contradictions_str}

THEIR EXACT WORDS TO WEAPONIZE:
{weapons_str}
{memory_str}
{insight_str}
{probe_line}
{grounding_instruction}

===================================================
PHASE: {phase.upper()} — {phase_description}
CONFIDENCE: {confidence}%
QUESTION: {questions_asked + 1} of {max_questions}
{tone_instruction}
{phase_rules}
===================================================

------------------------------------------------
STRATEGIC FOCUS: {required_vector.replace('_attack', '').upper()}
(If behavior doesn't dictate otherwise, use this angle)

THE READ:
{vector_desc}

------------------------------------------------

CRITICAL QUALITY RULES:
- If you have no clear signal, ask a FACTUAL grounding question. Do NOT infer psychology from nothing.
- If the user's answer is short, treat the brevity itself as evidence of concession, avoidance, or defense.
- Your response must be SPECIFIC to this decision. If it could apply to any decision, REWRITE IT.
- Every line must do exactly one job: reveal motive, expose contradiction, or narrow the real decision.
- If you would reuse the same clue without going deeper, do not ask it.

YOUR MOVE:
Read their last answer. What did they reveal? What did they avoid? Attack that.
Use their exact words against them. 80% observations, 20% questions.

Respond ONLY with JSON:
{{{{
    "spoken_statement": "your response — observation, question, or silence",
    "type": "observation|question|silence",
    "purpose": "{required_vector}",
    "vector": "{required_vector.replace('_attack', '')}",
    "uses_their_words": "exact phrase from their answer you're weaponizing",
    "evidence_quotes": ["exact quotes used in the statement"],
    "what_this_exposes": "what their response will reveal",
    "reason_to_continue": "one short sentence saying what new signal this line is trying to extract",
    "internal_deduction": "private step in the case you are building"
}}}}
==================================================="""


# ─── Legacy Compatibility ─────────────────────────────────────────────────────
# The old NEXT_QUESTION_PROMPT template for anything that still imports it.
# The service should use build_next_question_prompt() instead.

NEXT_QUESTION_PROMPT = f"""{PersonaConfig.CORE_IDENTITY}

{PersonaConfig.ATTACK_VECTORS}

{PersonaConfig.ESCALATION_RULES}

===================================================
SUBJECT'S DECISION: "{{query}}"

CONVERSATION:
{{formatted_history}}
===================================================

CURRENT PROFILE:
{{profile_snapshot}}

===================================================
PHASE: {{phase}}
{{phase_description}}

CONFIDENCE: {{confidence}}%
QUESTIONS: {{questions_asked}}/{{max_questions}}

LAST ANALYSIS SUGGESTED: {{probe_suggestion}}
===================================================

YOUR NEXT ATTACK:

Look at their last answer. What did they reveal? What did they avoid?

Respond ONLY with JSON:
{{{{
    "text": "your attack question — short, uses their words, hurts",
    "purpose": "vanity_attack|fear_attack|competence_attack|insecurity_attack",
    "vector": "vanity|fear|competence|insecurity",
    "uses_their_words": "exact phrase you're weaponizing",
    "what_this_exposes": "what their answer will reveal"
}}}}
==================================================="""


def format_history(history: List[Dict]) -> str:
    """Format conversation for prompts."""
    if not history:
        return "  (no conversation yet)"

    lines = []
    for i, h in enumerate(history, 1):
        q = h.get("question", h.get("text", ""))
        a = h.get("answer", "")
        lines.append(f"  Q{i}: {q}")
        lines.append(f"  A{i}: {a}")
        lines.append("")
    return "\n".join(lines)
