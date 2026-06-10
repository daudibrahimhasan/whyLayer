"""
Interrogation Service v3 — Fully Dynamic, No Hardcoded Questions
"""

import json
import logging
import re
import asyncio
import difflib
from typing import Optional, List, Dict

from services.llm_service import api_client, safe_llm_call
from services.answer_analyzer import AnswerAnalyzer
from prompts.interrogation import (
    INITIAL_QUESTIONS_PROMPT,
    NEXT_QUESTION_PROMPT,        # kept for fallback
    build_next_question_prompt,  # dynamic prompt builder
    get_interrogation_system_prompt,  # static system prompt
    PHASES,
    get_phase,
    format_history,
)
from prompts.classification import (
    CLASSIFICATION_PROMPT,
    get_min_questions_for_classification,
)

logger = logging.getLogger(__name__)

# ─── Classification Prompt ───────────────────────────────────────────────────


class InterrogationService:
    """Orchestrates fully dynamic LLM-powered interrogation."""

    MIN_QUESTIONS = 3
    MAX_QUESTIONS = 7
    MAX_TURNS_GENERIC = 5
    MAX_TURNS_DEEP = 7
    HARD_CAP = 7
    CONFIDENCE_THRESHOLD = 65
    MAX_RETRIES = 2
    MIN_SCORE = 65
    SIMILARITY_THRESHOLD = 0.65  # Reject questions >65% similar to previous ones
    QUALITY_ACCEPT_THRESHOLD = 55
    QUALITY_REJECT_THRESHOLD = 20

    # Attack vectors for rotation
    ALL_VECTORS = ["vanity_attack", "fear_attack", "competence_attack", "insecurity_attack"]

    # FIX 8: Sanity filter — lines that cross guardrails
    BANNED_PHRASES = [
        "you are broken", "you are nothing", "you are worthless",
        "kill yourself", "you deserve to suffer", "you are pathetic",
        "nobody loves you", "you will never", "you are a failure as a person",
        "you disgust me",
    ]
    LOW_INFO_SIGNALS = {"idk", "i dont know", "i don't know", "yea", "yeah", "maybe", "no", "yes"}
    GENERIC_FALLBACK_BANS = [
        "what exactly are you trying to decide",
        "can you clarify",
        "help me understand",
        "that wasn't an answer",
    ]
    PERSONA_FALLBACK_LINES = [
        "You're answering around it.",
        "That explains what. Not why.",
        "You avoided the part that matters.",
        "That hesitation already narrowed it.",
        "So that's the surface. Not the reason.",
        "You're describing it. Not deciding it.",
        "You answered the surface, not the point.",
        "That explains the action, not the reason.",
        "You keep answering around it.",
        "Then the real question is not contact. It's consequence.",
    ]

    def __init__(self, llm_service_instance=None):
        self.llm = llm_service_instance if llm_service_instance else api_client
        self._analyzers: Dict[str, AnswerAnalyzer] = {}
        self._question_history: Dict[str, List[str]] = {}  # session_id -> list of questions asked
        self._used_vectors: Dict[str, List[str]] = {}  # session_id -> list of vectors used
        self._topic_categories: Dict[str, str] = {}  # session_id -> topic category
        self._invalidated_vectors: Dict[str, set] = {}  # session_id -> set of invalidated vectors
        self._locked_vectors: Dict[str, Dict] = {}
        self._hypotheses: Dict[str, str] = {}
        self._session_modes: Dict[str, str] = {}  # FIX 1: Track grounding vs attack mode
        self._insights_sent: Dict[str, bool] = {}  # FIX 9: Track if mid-session insight was sent
        self._min_questions: Dict[str, int] = {}  # session_id -> dynamic min questions
        self._low_info_streaks: Dict[str, int] = {}
        self._signal_progress: Dict[str, List[bool]] = {}
        self._clue_usage: Dict[str, Dict[str, List[str]]] = {}
        self._last_reason_to_continue: Dict[str, str] = {}

    def _ensure_session(self, session_id):
        if session_id not in self._question_history:
            self._question_history[session_id] = []
            self._used_vectors[session_id] = []
            self._invalidated_vectors[session_id] = set()
            self._low_info_streaks[session_id] = 0
            self._signal_progress[session_id] = []
            self._clue_usage[session_id] = {}
            self._last_reason_to_continue[session_id] = ""

    def _get_analyzer(self, session_id: str) -> AnswerAnalyzer:
        """Get or create an analyzer for this session."""
        if session_id not in self._analyzers:
            self._analyzers[session_id] = AnswerAnalyzer(self.llm)
        return self._analyzers[session_id]

    def _get_question_history(self, session_id: str) -> List[str]:
        """Get question history for this session."""
        if session_id not in self._question_history:
            self._question_history[session_id] = []
        return self._question_history[session_id]

    def _is_short_answer(self, answer: str) -> bool:
        return len(answer.strip().split()) <= 3

    def _is_low_information(self, answer: str) -> bool:
        return answer.strip().lower() in self.LOW_INFO_SIGNALS

    def _analyze_short_answer(self, answer: str, analyzer: AnswerAnalyzer) -> Dict:
        a = answer.lower().strip()
        signal = {"type": "neutral", "hidden": None, "escalate": False, "stop": False}

        if a in {"yea", "yeah", "yes"}:
            signal = {
                "type": "concession",
                "hidden": "accepting pressure without explanation",
                "escalate": True,
                "stop": analyzer.consecutive_evasions >= 1,
            }
        elif a in {"idk", "i dont know", "i don't know", "maybe"}:
            signal = {
                "type": "avoidance",
                "hidden": "refusing to confront the actual motive",
                "escalate": True,
                "stop": analyzer.consecutive_evasions >= 1,
            }
        elif len(a.split()) <= 2:
            signal = {
                "type": "defensive",
                "hidden": "minimal response to reduce exposure",
                "escalate": True,
                "stop": False,
            }

        return signal

    def _build_signal_snapshot(self, analyzer: AnswerAnalyzer, short_signal: Optional[Dict] = None) -> Dict[str, bool]:
        profile = analyzer.profile_data
        return {
            "motive": bool(profile.get("stated_reason")),
            "hidden_motive": bool(profile.get("real_motivation") or (short_signal or {}).get("hidden")),
            "fear": bool(profile.get("hidden_fear") or profile.get("core_fear")),
            "contradiction": bool(analyzer.contradictions),
            "real_decision": bool(profile.get("stated_reason") and (profile.get("real_motivation") or profile.get("hidden_fear"))),
        }

    def _record_signal_progress(self, session_id: str, snapshot: Dict[str, bool]) -> bool:
        known = sum(1 for v in snapshot.values() if v)
        history = self._signal_progress.setdefault(session_id, [])
        previous_best = max([0] + history)
        new_signal = known > previous_best
        history.append(known)
        self._signal_progress[session_id] = history[-4:]
        return new_signal

    def _get_session_mode(self, session_id: str, classification: Optional[Dict], analyzer: AnswerAnalyzer) -> str:
        current = self._session_modes.get(session_id)
        if current:
            if analyzer.consecutive_evasions >= 1 or self._low_info_streaks.get(session_id, 0) >= 1:
                self._session_modes[session_id] = "deep"
            return self._session_modes[session_id]

        topic = self._topic_categories.get(session_id, "general")
        decision_type = (classification or {}).get("decision_type", "personal")
        weight = (classification or {}).get("weight", "serious")

        mode = "generic"
        if weight != "lightweight" or decision_type == "personal" or topic in {"relationship", "health", "career", "finance"}:
            mode = "deep"

        self._session_modes[session_id] = mode
        return mode

    def _last_two_turns_new_signal(self, session_id: str) -> bool:
        history = self._signal_progress.get(session_id, [])
        if len(history) < 2:
            return True
        return history[-1] > history[-2] or (len(history) >= 3 and history[-2] > history[-3])

    def _insight_completeness(self, analyzer: AnswerAnalyzer, short_signal: Optional[Dict] = None) -> int:
        return sum(1 for v in self._build_signal_snapshot(analyzer, short_signal).values() if v)

    def _candidate_primary_job(self, candidate: Dict) -> Optional[str]:
        text = (candidate.get("text") or candidate.get("spoken_statement") or "").lower()
        expose = (candidate.get("what_this_exposes") or "").lower()
        combined = f"{text} {expose}"

        if any(token in combined for token in ["contradiction", "doesn't match", "not the same", "you said", "you keep"]):
            return "expose_contradiction"
        if any(token in combined for token in ["real question", "real decision", "consequence", "what this changes", "outcome"]):
            return "narrow_real_decision"
        if any(token in combined for token in ["want", "motive", "fear", "avoid", "priority", "protecting"]):
            return "reveal_motive"
        return None

    def _is_valid_candidate(self, candidate: Dict) -> bool:
        text = (candidate.get("text") or candidate.get("spoken_statement") or "").strip()
        if not text:
            return False

        lowered = text.lower()
        if any(bad in lowered for bad in self.GENERIC_FALLBACK_BANS):
            return False

        if len(text.split()) > 18:
            return False

        return self._candidate_primary_job(candidate) is not None

    def _can_use_clue(self, session_id: str, clue: str, angle: str) -> bool:
        if not clue:
            return True

        usage = self._clue_usage.setdefault(session_id, {})
        angles = usage.get(clue, [])
        if not angles:
            return True
        if angle in angles:
            return False
        if len(angles) >= 2:
            return False
        return True

    def _register_clue_use(self, session_id: str, clue: str, angle: str) -> None:
        if not clue:
            return
        usage = self._clue_usage.setdefault(session_id, {})
        usage.setdefault(clue, []).append(angle)
        usage[clue] = usage[clue][-3:]

    def _repeated_clue_attack_detected(self, session_id: str, candidate: Optional[Dict]) -> bool:
        if not candidate:
            return False
        clue = (candidate.get("uses_their_words") or "").strip()
        angle = self._candidate_primary_job(candidate) or "unknown"
        return not self._can_use_clue(session_id, clue, angle)

    def _persona_fallback(self, session_id: str, reason: str = "") -> Dict:
        index = len(self._get_question_history(session_id)) % len(self.PERSONA_FALLBACK_LINES)
        text = self.PERSONA_FALLBACK_LINES[index]
        if reason and "surface" in reason.lower():
            text = "That explains what. Not why."
        return {
            "text": text,
            "spoken_statement": text,
            "type": "observation",
            "purpose": "fallback",
            "vector": "fallback",
            "reason_to_continue": reason or "pressure the gap they avoided",
            "evidence_quotes": [],
        }

    def _should_stop_interrogation(
        self,
        session_id: str,
        analyzer: AnswerAnalyzer,
        turn_count: int,
        mode: str,
        latest_answer: str = "",
        candidate: Optional[Dict] = None,
        short_signal: Optional[Dict] = None,
    ) -> bool:
        if turn_count >= self.HARD_CAP:
            return True
        if mode == "generic" and turn_count >= self.MAX_TURNS_GENERIC:
            return True
        if mode == "deep" and turn_count >= self.MAX_TURNS_DEEP:
            return True
        if self._insight_completeness(analyzer, short_signal) >= 3:
            return True
        if not self._last_two_turns_new_signal(session_id):
            return True
        if self._low_info_streaks.get(session_id, 0) >= 2:
            return True
        if self._repeated_clue_attack_detected(session_id, candidate):
            return True

        answer_lower = latest_answer.strip().lower()
        if any(phrase in answer_lower for phrase in ["i want", "the real decision", "what i actually want", "i just want"]):
            return True

        return False

    # ─── FIX 1: Grounding Gate ─────────────────────────────────────────────


    # ─── FIX 8: Sanity Filter ─────────────────────────────────────────────
    def _sanity_check(self, text: str) -> bool:
        """Reject responses that cross ethical guardrails.
        Returns True if the text passes, False if it should be rejected.
        """
        text_lower = text.lower()
        for banned in self.BANNED_PHRASES:
            if banned in text_lower:
                print(f"[INTERROGATION] ⚠️ SANITY FILTER: Rejected '{text[:50]}...' (matched: '{banned}')")
                return False
        return True

    # ─── FIX 5: Relevance Check ──────────────────────────────────────────
    def _is_relevant(self, question: str, query: str, questions_asked: int = 0) -> bool:
        if questions_asked >= 3:
            return True

        stop_words = {"should","i","my","the","a","an","to","in","on","or","and","is","it","do","if","me"}
        keywords = [w.lower() for w in query.split() if len(w) > 2 and w.lower() not in stop_words]
        q = question.lower()
        return any(k in q for k in keywords) if keywords else True

    # ─── FIX 9: Mid-Session Insight Generator ────────────────────────────
    def _generate_mid_session_insight(self, analyzer: AnswerAnalyzer) -> Optional[Dict]:
        """Generate a 'What I See So Far' insight after enough data collected.
        Keeps users hooked by showing them patterns between questions.
        """
        profile = analyzer.profile_data
        insights = []
        
        if profile.get("evasion_type") and profile["evasion_type"] not in ("none", None):
            insights.append(f"You're {profile['evasion_type'].replace('_', ' ')} — not deciding.")
        
        if profile.get("hidden_fear"):
            insights.append(f"You keep circling around: {profile['hidden_fear']}.")
        
        if analyzer.contradictions:
            insights.append(f"You contradicted yourself: {analyzer.contradictions[-1]}")
        
        # Behavioral pattern from answer lengths
        if len(analyzer.answer_lengths) >= 3:
            trend = analyzer.answer_lengths[-3:]
            if all(l < 5 for l in trend):
                insights.append("Your answers are getting shorter. You're pulling away.")
            elif trend[-1] > trend[0] * 2:
                insights.append("You're getting more detailed. Something is surfacing.")
        
        if not insights:
            return None
        
        return {
            "type": "insight",
            "text": " ".join(insights[:2]),  # Max 2 insights, keep it punchy
            "label": "WHAT I SEE SO FAR",
        }

    def _is_valid_trap(self, text: str) -> bool:
        t = text.lower().strip()

        weak_patterns = [
            "how do you feel",
            "what do you think",
            "why now",
            "what changed",
            "how long",
        ]
        if any(p in t for p in weak_patterns):
            return False

        if len(t.split()) < 6:
            return False

        trap_markers = [
            "or",
            "even if",
            "still",
            "really",
            "actually",
            "prove",
            "avoiding",
            "hiding",
        ]
        return any(m in t for m in trap_markers)

    def _is_strong_observation(self, text: str) -> bool:
        text = text.lower().replace("’", "'")

        interpretation_markers = [
            "you already",
            "you're not",
            "you don't",
            "you keep",
            "that's not",
        ]

        # Must NOT be generic
        generic = [
            "something",
            "things",
            "stuff",
        ]

        # Must contain specificity (their words / context)
        specific = len(text.split()) >= 5

        return (
            any(m in text for m in interpretation_markers)
            and not any(g in text for g in generic)
            and specific
        )

    def _score_response(self, result: Dict, session_id: str, phase: str, query: str = "") -> int:
        """Score response quality (0-100)"""
        score = 0
        text = (result.get("text") or result.get("spoken_statement") or "").lower().strip()
        response_type = result.get("type", "question")
        reason_to_continue = (result.get("reason_to_continue") or "").strip().lower()
        primary_job = self._candidate_primary_job(result)

        if not text:
            return 0

        if not self._sanity_check(text):
            return 0

        if not primary_job:
            return 0

        if any(bad in text for bad in self.GENERIC_FALLBACK_BANS):
            return 0

        if not reason_to_continue or reason_to_continue == self._last_reason_to_continue.get(session_id, "").strip().lower():
            score -= 35

        # 1. Observation strength (40 pts)
        if response_type == "observation":
            if self._is_strong_observation(text):
                score += 40
            else:
                score += 10

        # 2. Trap quality (30 pts)
        if response_type == "question":
            if self._is_valid_trap(text):
                score += 30
            else:
                return 0

        # 3. Uses user words (15 pts)
        if result.get("uses_their_words"):
            score += 15

        # 4. Length discipline (10 pts)
        word_count = len(text.split())
        if 4 <= word_count <= 15:
            score += 10
        else:
            score -= 10

        # 5. Attack style bonus (+15 pts)
        attack_markers = [
            "you’re not",
            "you're not",
            "you keep",
            "you already",
            "that's not",
            "this isn't",
            "you don’t",
            "you don't",
            "you’re avoiding",
            "you're avoiding",
            "you’re delaying",
            "you're delaying",
        ]
        
        if any(w in text for w in attack_markers):
            score += 15
            
        if '"' in text or "'" in text:  # uses their words explicitly
            score += 10
            
        # 6. Penalize safe / neutral language (-20 pts)
        weak_language = [
            "it depends",
            "maybe",
            "you could",
            "consider",
            "it might",
            "sometimes",
        ]

        if any(w in text for w in weak_language):
            score -= 20

        query_keywords = [w.lower() for w in query.split() if len(w) > 2]
        if any(k in text for k in query_keywords):
            score += 15

        # Deduct repetition
        for prev in self._get_question_history(session_id):
            similarity = difflib.SequenceMatcher(None, text, prev.lower()).ratio()
            if similarity > 0.72:
                return 0

        clue = (result.get("uses_their_words") or "").strip()
        if clue and not self._can_use_clue(session_id, clue, primary_job):
            score -= 50

        # Phase correctness
        if phase == "extraction" and any(x in text for x in ["coward", "hiding", "delaying", "terrified"]):
            score -= 20
        if phase == "attack" and not any(x in text for x in ["you keep", "you're", "you already", "that's not"]):
            score -= 10

        return max(0, score)
    def _is_too_similar(self, new_question: str, session_id: str) -> bool:
        """Reject questions that are >65% similar to any previous question."""
        history = self._get_question_history(session_id)
        for prev in history:
            similarity = difflib.SequenceMatcher(
                None,
                new_question.lower(),
                prev.lower()
            ).ratio()
            if similarity > self.SIMILARITY_THRESHOLD:
                logger.info(f"[INTERROGATION] Rejected similar question ({similarity:.0%}): {new_question[:40]}...")
                return True
            
            # Semantic keyword overlap check
            # Split into words, remove small words
            stop_words = {"what", "why", "how", "when", "where", "who", "does", "did", "are", "is", "the", "a", "an", "to", "in", "on", "at", "for", "of", "with"}
            new_words = set(w for w in new_question.lower().split() if len(w) > 3 and w not in stop_words)
            prev_words = set(w for w in prev.lower().split() if len(w) > 3 and w not in stop_words)
            
            if new_words and prev_words:
                overlap = len(new_words & prev_words) / len(new_words)
                if overlap > 0.7:  # 70% of key words overlap
                    logger.info(f"[INTERROGATION] Rejected semantic duplicate ({overlap:.0%}): {new_question[:40]}...")
                    return True

        return False

    def _normalize_generated_response(self, result: Dict, history: List[Dict]) -> Dict:
        """Map the LLM contract to the app contract and force quote-trap formatting."""
        spoken_statement = (result.get("spoken_statement") or result.get("text") or "").strip()
        response_type = result.get("type", "question")
        evidence_quotes = [q.strip() for q in result.get("evidence_quotes", []) if isinstance(q, str) and q.strip()]
        exact_phrase = (result.get("uses_their_words") or "").strip()
        reason_to_continue = (result.get("reason_to_continue") or result.get("what_this_exposes") or "").strip()

        if history:
            latest_answer = history[-1].get("answer", "")
            if exact_phrase and exact_phrase not in latest_answer:
                exact_phrase = ""

        if exact_phrase and exact_phrase not in evidence_quotes:
            evidence_quotes.insert(0, exact_phrase)

        if response_type != "silence" and exact_phrase:
            quoted_phrase = f'"{exact_phrase}"'
            if quoted_phrase not in spoken_statement:
                spoken_statement = f"{quoted_phrase} {spoken_statement}".strip()

        result["spoken_statement"] = spoken_statement
        result["text"] = spoken_statement
        result["evidence_quotes"] = evidence_quotes[:2]
        result["reason_to_continue"] = reason_to_continue or "force a new layer"
        return result

    def _select_attack_vector(self, session_id: str, current_layer: str = "script") -> str:
        """Select attack vector based on topic category and usage history."""
        used = self._used_vectors.get(session_id, [])
        # HARD RULE: If we have a nerve hypothesis → stay on same vector
        if self._hypotheses.get(session_id) and used:
            return used[-1]

        # Check for locked vector first
        if session_id in self._locked_vectors:
            lock_info = self._locked_vectors[session_id]
            if lock_info["turns_remaining"] > 0:
                lock_info["turns_remaining"] -= 1
                return lock_info["vector"]

        used = self._used_vectors.get(session_id, [])
        last_used = used[-1] if used else None
        
        # Dont rotate. Stick and press.
        if current_layer in ("fog", "nerve") and last_used:
            return last_used

        invalidated = self._invalidated_vectors.get(session_id, set())
        topic = self._topic_categories.get(session_id, "general")
        
        # Topic-aware vector priorities
        # For relationships: fear > insecurity > competence > vanity (last resort)
        TOPIC_VECTORS = {
            "relationship": ["fear_attack", "insecurity_attack", "competence_attack", "vanity_attack"],
            "health": ["fear_attack", "insecurity_attack", "competence_attack", "vanity_attack"],
            "career": ["insecurity_attack", "competence_attack", "fear_attack", "vanity_attack"],
            "finance": ["fear_attack", "competence_attack", "insecurity_attack", "vanity_attack"],
            "purchase": ["vanity_attack", "fear_attack", "competence_attack", "insecurity_attack"],
            "entertainment": ["vanity_attack", "competence_attack", "fear_attack", "insecurity_attack"],
        }
        
        # Get ordered vectors for this topic (default = all equally weighted)
        ordered_vectors = TOPIC_VECTORS.get(topic, self.ALL_VECTORS)
        
        # For relationship/health: SKIP vanity entirely for first 6 questions
        # Also skip any vector that has been invalidated (e.g. user said "nobody knows")
        skip_vanity = (topic in ("relationship", "health") and len(used) < 6) or "vanity_attack" in invalidated
        
        candidates_pool = ordered_vectors
        if skip_vanity:
            candidates_pool = [v for v in ordered_vectors if v != "vanity_attack"]
        
        # Also limit validated invalidated vectors
        candidates_pool = [v for v in candidates_pool if v not in invalidated]
        if not candidates_pool:
            candidates_pool = ordered_vectors # Fallback to all if everything invalidated (unlikely)

        # Count usage
        usage = {v: used.count(v) for v in candidates_pool}
        
        # Get least-used vectors
        min_usage = min(usage.values()) if usage else 0
        least_used = [v for v in ordered_vectors if usage.get(v, 0) == min_usage]
        
        # Don't use same vector 2x in a row if possible
        last_used = used[-1] if used else None
        candidates = [v for v in least_used if v != last_used]
        
        if not candidates:
            candidates = [v for v in ordered_vectors if v != last_used]
        
        if not candidates:
            candidates = ordered_vectors
        
        selected = candidates[0]
        
        # Track usage
        if session_id not in self._used_vectors:
            self._used_vectors[session_id] = []
        self._used_vectors[session_id].append(selected)
        
        print(f"[INTERROGATION] Selected attack vector: {selected} (topic={topic}, history: {used})")
        return selected

    async def classify_decision(self, query: str) -> Dict:
        """Classify whether this is a real decision and its type."""
        prompt = CLASSIFICATION_PROMPT.format(query=query)
        
        for attempt in range(self.MAX_RETRIES):
            try:
                messages = [{"role": "user", "content": prompt}]
                response = self.llm.call_with_fallback(
                    messages=messages,
                    temperature=0.2,
                    prefer_groq=True,
                )
                result = self._parse_json(response)
                if result:
                    is_decision = result.get("is_decision", True)
                    category = result.get("topic_category", "general")
                    
                # ─── Heuristic Overrides ───
                # If specific keywords appear, force entertainment/lightweight
                # The LLM sometimes overthinks "is this a decision?"
                query_lower = query.lower()
                entertainment_keywords = {"watch", "movie", "anime", "series", "season", "episode", "game", "play"}
                
                if "entertainment" == category:
                        result["weight"] = "lightweight"
                
                elif any(k in query_lower for k in entertainment_keywords):
                        category = "entertainment"
                        result["topic_category"] = "entertainment"
                        result["weight"] = "lightweight"
                
                # REJECT GREETINGS EXPLICITLY
                if category == "greeting" or query_lower in ["hi", "hello", "hey", "yo"]:
                    result["is_decision"] = False
                    result["decision_type"] = "not_a_decision"
                    result["weight"] = "ignore" # Special flag for router
                    result["rejection_reason"] = "greeting"

                print(f"\n[INTERROGATION] --- Classification ---")
                print(f"Topic: {category}")
                print(f"Weight: {result.get('weight')}")
                print(f"Is Decision: {result.get('is_decision')}")
                print(f"Decision Type: {result.get('decision_type')}")
                print(f"---------------------------------------\n")
                
                logger.info(
                    f"[INTERROGATION] Classified: {category} ({result.get('weight')}) / "
                    f"{'DECISION' if result.get('is_decision') else 'NOT A DECISION'}"
                )
                return result
            except Exception as e:
                logger.warning(f"[INTERROGATION] Classification attempt {attempt + 1} failed: {e}")

        # Fallback: assume it's a decision to avoid blocking
        return {
            "is_decision": True,
            "decision_type": "personal",
            "topic_category": "general",
            "options": [],
            "keywords": [],
            "emotional_hints": [],
            "urgency": "unknown",
        }

    async def generate_initial_questions(
        self,
        query: str,
        session_id: str,
        classification: Dict,
    ) -> List[Dict]:
        """Generate first 3 questions dynamically — no hardcoded fallbacks."""
        self._ensure_session(session_id)
        
        # Store topic category for vector selection later
        topic = classification.get("topic_category", "general")
        self._topic_categories[session_id] = topic
        self._min_questions[session_id] = get_min_questions_for_classification(
            classification.get("decision_type", "personal"), topic
        )
        self._session_modes[session_id] = self._get_session_mode(
            session_id, classification, self._get_analyzer(session_id)
        )
        
        prompt = INITIAL_QUESTIONS_PROMPT.format(
            query=query,
            decision_type=classification.get("decision_type", "personal"),
            topic_category=topic,
        )

        banned = ["why now", "what changed", "how long", "what do you want"]
        
        for attempt in range(self.MAX_RETRIES):
            try:
                messages = [
                    {"role": "system", "content": get_interrogation_system_prompt()},
                    {"role": "user", "content": prompt}
                ]
                safe_result = await asyncio.to_thread(
                    safe_llm_call,
                    self.llm.call_for_interrogation,
                    messages=messages,
                    temperature=0.7,
                )
                
                print("---- DEBUG ----")
                print("RAW RESPONSE: HIDDEN IN ASYNC WRAPPER")
                print("PARSED:", safe_result)
                print("---------------")
                
                result = safe_result.get("raw")
                if result and "questions" in result:
                    questions = result["questions"]
                    
                    # Store hypothesis
                    if "initial_read" in result:
                        self._hypotheses[session_id] = result["initial_read"]
                    
                    # Anti-generic filter
                    has_generic = False
                    for q in questions:
                        q_text = q.get("text", "").lower()
                        if any(b in q_text for b in banned):
                            has_generic = True
                            break
                    if has_generic and attempt < self.MAX_RETRIES - 1:
                        print("[INTERROGATION] Generic phrasing detected. Regenerating...")
                        continue

                    # Enforce observations (must be >= 2)
                    obs_count = sum(1 for q in questions if "?" not in q.get("text", ""))
                    if obs_count < 2 and len(questions) >= 2:
                        print(f"[INTERROGATION] Only {obs_count} observations. Forcing compliance.")
                        for i in range(2 - obs_count):
                            questions[i]["text"] = questions[i].get("text", "").replace("?", ".")

                    strong_obs = sum(
                        1 for q in questions
                        if "?" not in q.get("text", "") and self._is_strong_observation(q.get("text", ""))
                    )

                    if strong_obs < 1 and attempt < self.MAX_RETRIES - 1:
                        print("[INTERROGATION] Weak observations detected. Regenerating...")
                        continue

                    # Hard check for trap quality
                    valid_traps = sum(
                        1 for q in questions
                        if "?" in q.get("text", "") and self._is_valid_trap(q.get("text", ""))
                    )

                    if valid_traps == 0 and attempt < self.MAX_RETRIES - 1:
                        print("[INTERROGATION] No valid traps. Regenerating...")
                        continue

                    # Force chaining: Q2 builds on Q1, Q3 corners
                    if len(questions) >= 3:
                        q1 = questions[0]["text"]
                        q2 = questions[1]["text"]
                        q3 = questions[2]["text"]

                        # Light chaining enforcement
                        if not any(word in q2.lower() for word in q1.lower().split()[:2]):
                            questions[1]["text"] = f"{q1.split('.')[0]}. {q2}"

                        if not any(word in q3.lower() for word in q2.lower().split()[:2]):
                            questions[2]["text"] = f"{q2.split('.')[0]}. {q3}"


                    print(f"\n[INTERROGATION] --- Initial Questions ---")
                    for i, q in enumerate(questions):
                        print(f" Q{i+1}: {q.get('text')}")
                    print(f"-----------------------------------------\n")
                    
                    logger.info(f"[INTERROGATION] Generated {len(questions)} initial questions")
                    return questions
            except Exception as e:
                logger.warning(f"[INTERROGATION] Initial questions attempt {attempt + 1} failed: {e}")

        # Dynamic fallback — still references the decision
        logger.warning("[INTERROGATION] All attempts failed. Using dynamic fallback.")
        return self._generate_dynamic_fallback_initial(query)

    def _generate_dynamic_fallback_initial(self, query: str) -> List[Dict]:
        """Generate context-aware fallback questions when LLM fails."""
        query_lower = query.lower()
        if "ex" in query_lower or "text" in query_lower:
            return [
                {"text": "You're not asking because you miss conversation.", "purpose": "extraction", "type": "observation"},
                {"text": "What are you hoping the text changes?", "purpose": "extraction", "type": "question"},
                {"text": "So this is about what silence has been saying to you.", "purpose": "transition", "type": "observation"},
            ]

        return [
            {
                "text": "You're not asking this for the reason you gave.",
                "purpose": "extraction",
                "type": "observation",
            },
            {
                "text": "What outcome are you actually trying to force?",
                "purpose": "extraction",
                "type": "question",
            },
            {
                "text": "You're describing the option. Not the consequence you fear.",
                "purpose": "transition",
                "type": "observation",
            },
        ]

    async def process_answer_and_get_next(
        self,
        query: str,
        session_id: str,
        history: List[Dict],
        topic_category: Optional[str] = None,
    ) -> Dict:
        """Process answer, update profile, generate next question dynamically."""
        self._ensure_session(session_id)
        
        # Fixing the 'Topic Loss' bug:
        # If topic passed (from frontend/router), update our session.
        # If not passed and we don't have it (restart), try to infer it.
        if topic_category:
            self._topic_categories[session_id] = topic_category
        elif session_id not in self._topic_categories:
            # Fallback heuristic: check query/history for relationship keywords
            text_to_check = (query + " " + " ".join(h.get("question") or h.get("text") or "" for h in history)).lower()
            rel_keywords = {"ex", "girlfriend", "boyfriend", "wife", "husband", "breakup", "divorce", "dating", "love", "partner", "crush"}
            if any(k in text_to_check for k in rel_keywords):
                self._topic_categories[session_id] = "relationship"
                print(f"[INTERROGATION] Inferred topic 'relationship' from context.")
            else:
                self._topic_categories[session_id] = "general" # Default
        
        analyzer = self._get_analyzer(session_id)
        confidence = analyzer.confidence if analyzer else 0
        questions_asked = len(history)
        min_questions = self._min_questions.get(session_id, self.MIN_QUESTIONS)
        session_mode = self._get_session_mode(session_id, None, analyzer)
        short_signal = None

        # ─── Step 1: Analyze the latest answer ────────────────────────
        if history:
            latest = history[-1]
            question = latest.get("question") or latest.get("text") or ""
            answer = latest.get("answer", "")

            print(f"\n[INTERROGATION] <<< Answer Received <<<")
            print(f" Question: {question}")
            print(f" Answer:   {answer}")
            print(f"------------------------------------------\n")

            # FIX 11: Stop escalating off one-word junk
            clean = answer.strip().lower()
            if self._is_low_information(answer):
                self._low_info_streaks[session_id] = self._low_info_streaks.get(session_id, 0) + 1
            else:
                self._low_info_streaks[session_id] = 0

            if self._is_short_answer(answer):
                short_signal = self._analyze_short_answer(answer, analyzer)
                if short_signal.get("hidden") and not analyzer.profile_data.get("real_motivation"):
                    analyzer.profile_data["real_motivation"] = short_signal["hidden"]
            else:
                await analyzer.analyze(
                    query=query,
                    question=question,
                    answer=answer,
                    history=history[:-1],
                )
            self._record_signal_progress(
                session_id,
                self._build_signal_snapshot(analyzer, short_signal),
            )
            
            # Smart Vector Invalidation
            # If user says "nobody knows", "secret", "private" -> Vanity is invalid (no audience)
            ans_lower = answer.lower()
            if any(w in ans_lower for w in ("nobody", "no one", "private", "secret", "just me")):
                if session_id not in self._invalidated_vectors:
                    self._invalidated_vectors[session_id] = set()
                self._invalidated_vectors[session_id].add("vanity_attack")
                print(f"[INTERROGATION] Invalidated 'vanity_attack' based on user response.")

        confidence = analyzer.confidence
        current_layer = analyzer.profile_data.get("current_layer", "script")
        evasion = analyzer.profile_data.get("evasion_type", "none")
        if analyzer.consecutive_evasions >= 1 or self._low_info_streaks.get(session_id, 0) >= 1:
            self._session_modes[session_id] = "deep"
        session_mode = self._session_modes.get(session_id, session_mode)
        session_cap = self.MAX_TURNS_GENERIC if session_mode == "generic" else self.MAX_TURNS_DEEP
        
        print(f"[INTERROGATION] Profile Analysis: Layer={current_layer}, Confidence={confidence}%, Evasion={evasion}")
        
        # FIX 4: Lock vector EARLIER — at confidence > 40 instead of 60
        # This prevents random vector rotation that feels disconnected
        if (current_layer in ("fog", "nerve") or confidence >= 40) and evasion == "none" and session_id not in self._locked_vectors:
            last_q = history[-1].get("question", {}) if history else {}
            if isinstance(last_q, dict):
                vector_to_lock = last_q.get("vector", "fear_attack")
            else:
                vector_to_lock = "fear_attack"
            self._locked_vectors[session_id] = {
                "vector": vector_to_lock,
                "turns_remaining": 3  # FIX 4: Extended from 2 to 3 — stick longer
            }
            print(f"[INTERROGATION] FIX 4: Vector LOCKED at {vector_to_lock} (confidence={confidence}, layer={current_layer})")
        
        logger.info(
            f"[INTERROGATION] Q{questions_asked} | Layer: {current_layer} | "
            f"Confidence: {confidence}% | Evasion: {evasion}"
        )

        # ─── Step 2: Decide whether to continue (Check Termination BEFORE Evasion) ───
        if self._should_stop_interrogation(
            session_id,
            analyzer,
            questions_asked,
            session_mode,
            latest_answer=history[-1].get("answer", "") if history else "",
            short_signal=short_signal,
        ):
            return {"status": "verdict_ready", "reason": "stop_heuristic"}

        if questions_asked >= session_cap:
            print(f"[INTERROGATION] !!! Decision to end: Max questions reached ({session_cap})")
            logger.info("[INTERROGATION] Max questions reached. Forcing verdict.")
            return {"status": "verdict_ready", "reason": "max_questions"}

        # Smarter ending: require higher confidence if still in fog layer
        if questions_asked >= min_questions:
            # If in nerve layer with high confidence, end
            if current_layer == "nerve" and confidence >= 75:
                print(f"[INTERROGATION] !!! Decision to end: Nerve reached ({confidence}%)")
                return {"status": "verdict_ready", "reason": "nerve_reached"}
            
            # If in fog but lower confidence, keep probing (need 70% in fog)
            if current_layer == "fog" and confidence >= 70 and questions_asked >= 5:
                print(f"[INTERROGATION] !!! Decision to end: Fog layer complete ({confidence}%)")
                return {"status": "verdict_ready", "reason": "confidence_met"}
            
            # High confidence regardless of layer
            if confidence >= 80:
                print(f"[INTERROGATION] !!! Decision to end: High confidence ({confidence}%)")
                return {"status": "verdict_ready", "reason": "high_confidence"}

        # Emergency: stuck at low confidence
        if questions_asked >= 7 and confidence < 30:
            logger.warning(f"[INTERROGATION] Emergency force at Q{questions_asked}")
            return {"status": "verdict_ready", "reason": "emergency_force"}

        # ─── FIX 9: Mid-Session Insight (after Q3-Q4, once per session) ───
        if questions_asked in (3, 4) and not self._insights_sent.get(session_id):
            insight = self._generate_mid_session_insight(analyzer)
            if insight:
                self._insights_sent[session_id] = True
                print(f"[INTERROGATION] FIX 9: Sending mid-session insight: {insight['text'][:60]}...")

        # ─── Step 3: Check for evasion (Only if not ending) ─────────────────
        # If user evades, we callout before generating regular next question
        if history:
            latest = history[-1]
            answer = latest.get("answer", "")
            question = latest.get("question", latest.get("text", ""))
            
            # Determine previous question type (observation vs question)
            # If it doesn't end in '?', it's likely an observation
            # This prevents "yea" to "You choose sadness" being flagged as evasion
            prev_type = "question"
            if question and not question.strip().endswith("?"):
                prev_type = "observation"
                print(f"[INTERROGATION] Previous response identified as OBSERVATION (no '?').")

            evasion_result = analyzer.detect_evasion(
                answer, 
                question, 
                history[:-1], 
                response_type=prev_type
            )
            
            # None means valid response (e.g. short reply to observation)
            if evasion_result is None:
                evasion_result = {"type": "none", "severity": "none", "response": None}

            # Confusion -- NOT evasion. Switch vector and rephrase.
            if evasion_result["type"] == "confusion":
                print(f"[INTERROGATION] User confused by question. Switching vector.")
                # Don't call them out — just move to a different angle
                # The next question generation will use a new vector automatically
            elif evasion_result["type"] in ("non_answer", "one_word", "repetition", "echo"):
                if analyzer.consecutive_evasions >= 2:
                    print(f"[INTERROGATION] !!! CONSECUTIVE EVASION DETECTED! Letting LLM punish.")
                    # Do not early return, fall through to attack phase override.
                else:
                    print(f"[INTERROGATION] !!! EVASION DETECTED: {evasion_result['type']}")
                    print(f"[INTERROGATION] Callout: {evasion_result['response']}")
                    
                    return {
                        "status": "in_progress",
                        "question": {
                            "text": evasion_result["response"],
                            "purpose": "evasion_callout",
                            "vector": "insecurity",
                        },
                        "phase": "transition",
                        "questions_asked": questions_asked,
                        "exposure_confidence": confidence,
                        "is_callout": True,
                    }

        # ─── Step 4: Generate next question with dedup ─────────────────────
        phase = get_phase(questions_asked, confidence, analyzer.consecutive_evasions)
        phase_info = PHASES[phase]
        phase_description = (
            phase_info.get("goal", phase)
            if isinstance(phase_info, dict)
            else str(phase_info)
        )
        profile_snapshot = analyzer.get_profile_snapshot()
        
        # FIX 1: Override phase to 'extraction' if still in grounding mode
        if session_mode == "grounding":
            phase = "extraction"
            phase_info = PHASES["extraction"]
            phase_description = (
                phase_info.get("goal", phase)
                if isinstance(phase_info, dict)
                else str(phase_info)
            )
            print(f"[INTERROGATION] FIX 1: GROUNDING MODE — forcing extraction phase")
        
        # Select required vector for rotation
        required_vector = self._select_attack_vector(session_id, current_layer)
        question_history = self._get_question_history(session_id)

        # FIX 6: Inject user memory into profile snapshot for prompt
        from services.user_profile_service import get_user
        # user_id not directly available here — use session fingerprint or 'default'
        user_memory = get_user("default_user")
        if user_memory.get("total_sessions", 0) > 0:
            profile_snapshot["memory_context"] = {
                "dominant_pattern": user_memory.get("dominant_pattern"),
                "dominant_vector": user_memory.get("dominant_vector"),
                "past_fears": user_memory.get("hidden_fears", [])[-3:],
                "total_sessions": user_memory.get("total_sessions", 0),
            }
            print(f"[INTERROGATION] FIX 6: Memory injected — pattern: {user_memory.get('dominant_pattern')}")

        # FIX 9: Attach mid-session insight to profile for prompt builder
        if self._insights_sent.get(session_id):
            insight = self._generate_mid_session_insight(analyzer)
            if insight:
                profile_snapshot["mid_session_insight"] = insight["text"]

        # Compress history into a weakness-only cold case file.
        prompt_history = history[-2:]
        if len(history) > 2:
            weakness_lines = profile_snapshot.get("weakness_summary", [])
            summary_entry = {
                "question": "[COLD CASE FILE]",
                "answer": " | ".join(weakness_lines) if weakness_lines else "Previous turns reduced to profile deltas.",
            }
            prompt_history = [summary_entry] + prompt_history
            logger.info(f"[INTERROGATION] History compressed to cold case file: {len(history)} → {len(prompt_history)} entries")

        phase_mode = phase
        
        # FIX 4: EVASION -> IMMEDIATE PUNISH
        if analyzer.consecutive_evasions >= 2:
            phase_mode = "attack"
            print("[INTERROGATION] FIX 4: Punishing consecutive evasions. FORCING ATTACK.")
        
        if phase_mode == "extraction":
            tone_instruction = """
PHASE: EXTRACTION

- No aggression
- No accusations
- Use user's words
- Ask clean, sharp questions
- Goal: make them reveal something real

Bad:
"You're lying to yourself"

Good:
"You said 'stable.' What are you protecting?"
"""
        elif phase_mode == "transition":
            tone_instruction = """
PHASE: TRANSITION

- Start making observations (not full attacks)
- Interpret behavior, don't insult
- Slight discomfort

Good:
"You keep describing outcomes, not what you want."
"You haven't said why YOU want this."

Goal:
Make them feel seen, not attacked yet.
"""
        elif phase_mode == "attack":
            tone_instruction = """
PHASE: ATTACK

- Use their exact words against them
- Call out contradictions
- Force binary traps
- If they evade → expose it immediately

Examples:
"You said 'I think I could.' That's not belief."
"You're not deciding. You're avoiding the outcome."

Every line must:
- corner them
- expose something
- remove escape
"""
            # FORCE PERSONAL ATTACKS
            memory_attack = ""
            if profile_snapshot.get("weaponizable_phrases"):
                memory_attack += f"\nUse this exact phrase against them: {profile_snapshot['weaponizable_phrases'][0]}"
            
            if profile_snapshot.get("hidden_fear"):
                memory_attack += f"\nTarget this fear directly: {profile_snapshot['hidden_fear']}"
                
            tone_instruction += "\n" + memory_attack

        # FIX 1: Grounding mode instruction override
        grounding_instruction = ""
        if session_mode == "grounding":
            grounding_instruction = (
                "\n\nGROUNDING MODE ACTIVE: First understand reality. "
                "No assumptions. No accusations yet. Ask sharp but FACTUAL questions "
                "about their situation. Establish what is real before interpreting what is hidden."
            )

        # Use the new dynamic prompt builder
        system_prompt = get_interrogation_system_prompt()
        user_prompt = build_next_question_prompt(
            query=query,
            history=prompt_history,
            profile_snapshot=profile_snapshot,
            phase=phase_mode,
            phase_description=phase_description,
            confidence=confidence,
            questions_asked=questions_asked,
            max_questions=session_cap,
            required_vector=required_vector,
            question_history=question_history,
            probe_suggestion=analyzer.probe_suggestion,
            initial_hypothesis=self._hypotheses.get(session_id),
            tone_instruction=tone_instruction,           # FIX 7: Adaptive tone
            grounding_instruction=grounding_instruction,  # FIX 1: Grounding mode
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # PASS 7: Generate next question with dedup
        MAX_RETRIES = 2
        best_candidate = None
        best_score = -1

        # FIX 5: Reduce candidates from 2 → 1 when confidence is high enough
        # High confidence means we already have strong signal — less exploration needed
        num_candidates = 1 if confidence > 50 else 2
        print(f"[INTERROGATION] FIX 5: Using {num_candidates} candidate(s) (confidence={confidence})")

        for attempt in range(MAX_RETRIES):
            candidates = []
            for cand_idx in range(num_candidates):
                try:
                    messages_with_noise = messages + [{"role": "system", "content": f"variation_seed: {cand_idx}"}]
                    safe_result = await asyncio.to_thread(
                        safe_llm_call,
                        self.llm.call_for_interrogation,
                        messages=messages_with_noise,
                        temperature=0.7 + (attempt * 0.1),
                        max_tokens=300
                    )
                    
                    print("---- DEBUG ----")
                    print("RAW RESPONSE: HIDDEN IN ASYNC WRAPPER")
                    print("PARSED:", safe_result)
                    print("---------------")
                    
                    parsed = safe_result.get("raw") or safe_result
                    if not parsed or not (parsed.get("spoken_statement") or parsed.get("text")):
                        continue
                    
                    parsed = self._normalize_generated_response(parsed, history)
                    score = self._score_response(parsed, session_id, phase_mode, query=query)

                    if not self._is_valid_candidate(parsed):
                        score = 0

                    # Deduplication check
                    if self._is_too_similar(parsed.get("text", ""), session_id):
                        score -= 50
                    
                    # FIX 8: Sanity filter — reject if it crosses guardrails
                    if not self._sanity_check(parsed.get("text", "")):
                        score = -100  # Kill this candidate
                    
                    # FIX 5: Relevance check — penalize irrelevant questions
                    if not self._is_relevant(parsed.get("text", ""), query, questions_asked):
                        score -= 30
                        print(f"[CANDIDATE] Penalized for low relevance to query")
                    
                    # FIX 2: Reject garbage below threshold
                    if score < self.QUALITY_REJECT_THRESHOLD:
                        print(f"[CANDIDATE] REJECTED (score {score} < {self.QUALITY_REJECT_THRESHOLD}): {parsed.get('text', '')[:60]}...")
                        continue
                    
                    print(f"[CANDIDATE] Attempt {attempt} | Cand {cand_idx} | Score: {score} | {parsed.get('text')[:60]}...")
                    candidates.append((score, parsed))
                except Exception as e:
                    logger.warning(f"[INTERROGATION] Candidate generation failed: {e}")

            if not candidates:
                continue
                
            current_best_score, current_best_cand = max(candidates, key=lambda x: x[0])
            
            if current_best_score > best_score:
                best_score = current_best_score
                best_candidate = current_best_cand

            # FIX 2: Raised quality acceptance threshold from 50 → 75
            if best_score >= self.QUALITY_ACCEPT_THRESHOLD:
                break

        # Final acceptance logic
        if not best_candidate:
             return {"status": "verdict_ready", "reason": "no_viable_candidate"}

        result = best_candidate
        question_text = result["text"]

        if self._repeated_clue_attack_detected(session_id, result):
            return {"status": "verdict_ready", "reason": "repeated_clue_attack"}
        
        if not question_text or len(question_text.strip()) < 5:
            fallback = self._persona_fallback(session_id, result.get("reason_to_continue", ""))
            question_text = fallback["text"]
            result.update(fallback)
            
        print(f"[QUALITY] Selected best candidate with score: {best_score}")
        # Pressure escalation model
        if confidence > 60:
            result["text"] = result["text"].replace("...", ".")
            question_text = result["text"]
            
        if confidence > 75:
            import re
            result["text"] = re.sub(r'\bmaybe\b', '', result["text"], flags=re.IGNORECASE).replace("  ", " ")
            question_text = result["text"]

        # Enforce chaining from last question
        if history:
            last_q = history[-1].get("question", "")
            first_word = last_q.split(" ")[0].lower() if last_q else ""
            if first_word and first_word not in question_text.lower():
                print("[INTERROGATION] ⚠️ Weak chaining. Reinforcing context.")
                result["text"] = f"{first_word.capitalize()}... {question_text}"
                question_text = result["text"]

        # === ENFORCE VECTOR ===
        returned_vector = result.get("purpose", "")
        if returned_vector != required_vector:
            print(f"[INTERROGATION] ⚠️ LLM returned {returned_vector} instead of {required_vector}. Overriding.")
            result["purpose"] = required_vector
        
        response_type = result.get("type", "question")
        self._last_reason_to_continue[session_id] = result.get("reason_to_continue", "")
        clue = (result.get("uses_their_words") or "").strip()
        angle = self._candidate_primary_job(result) or "unknown"
        self._register_clue_use(session_id, clue, angle)
        
        # Accept and track this question
        self._get_question_history(session_id).append(question_text)
        
        print(f"\n[INTERROGATION] >>> Next Response Generated >>>")
        print(f" Phase:   {phase}")
        print(f" Mode:    {session_mode}")
        print(f" Vector:  {required_vector}")
        print(f" Type:    {response_type}")
        print(f" Text:    {question_text}")
        print(f" Purpose: {result.get('purpose')}")
        print(f" Score:   {best_score}")
        print(f"-----------------------------------------------\n")

        logger.info(f"[INTERROGATION] Next Q ({phase}): {question_text[:60]}... | Purpose: {result.get('purpose', '?')}")
        
        # FIX 9: Attach mid-session insight if available (alongside the question)
        response = {
            "status": "in_progress",
            "question": result,
            "phase": phase,
            "questions_asked": questions_asked,
            "exposure_confidence": confidence,
        }
        
        if questions_asked in (3, 4) and self._insights_sent.get(session_id):
            insight = self._generate_mid_session_insight(analyzer)
            if insight:
                response["insight"] = insight
        
        return response

    def _generate_dynamic_fallback_next(
        self, 
        phase: str, 
        evasion_type: str, 
        probe_suggestion: Optional[str],
        history: List[Dict]
    ) -> Dict:
        """Generate context-aware fallback when LLM fails."""
        
        # Reference last answer if available
        last_answer = ""
        if history:
            last_answer = history[-1].get("answer", "")[:50]

        # Evasion-aware fallbacks
        if evasion_type == "humor":
            return {
                "text": "You used humor to dodge the part that matters.",
                "spoken_statement": "You used humor to dodge the part that matters.",
                "purpose": "evasion_callout",
                "vector": "insecurity",
                "reason_to_continue": "strip away the dodge",
                "evidence_quotes": []
            }
        elif evasion_type == "vagueness":
            return {
                "text": "You blurred it right where the answer should be.",
                "spoken_statement": "You blurred it right where the answer should be.",
                "purpose": "evasion_callout", 
                "vector": "fear",
                "reason_to_continue": "make them name the avoided point",
                "evidence_quotes": []
            }
        elif evasion_type == "deflection":
            return {
                "text": "You answered beside it. Not through it.",
                "spoken_statement": "You answered beside it. Not through it.",
                "purpose": "evasion_callout",
                "vector": "insecurity",
                "reason_to_continue": "pull them back to the real axis",
                "evidence_quotes": []
            }
        elif evasion_type == "aggression":
            return {
                "text": "That reaction narrowed it more than the answer did.",
                "spoken_statement": "That reaction narrowed it more than the answer did.",
                "purpose": "evasion_callout",
                "vector": "insecurity",
                "reason_to_continue": "use the reaction as evidence",
                "evidence_quotes": []
            }

        # Phase-aware fallbacks
        if phase == "attack":
            return {
                "text": "You already narrowed it by what you avoided saying.",
                "spoken_statement": "You already narrowed it by what you avoided saying.",
                "purpose": "attack",
                "vector": "fear",
                "reason_to_continue": "convert avoidance into the decision frame",
                "evidence_quotes": []
            }
        elif phase == "transition":
            return {
                "text": "You're describing events, not what outcome you're trying to avoid.",
                "spoken_statement": "You're describing events, not what outcome you're trying to avoid.",
                "purpose": "transition",
                "vector": "fear",
                "reason_to_continue": "move from surface facts to the feared consequence",
                "evidence_quotes": []
            }
        
        # Default probe
        return {
            "text": "That explains what. Not why.",
            "spoken_statement": "That explains what. Not why.",
            "purpose": "extraction",
            "vector": "insecurity",
            "reason_to_continue": "separate the surface answer from the motive",
            "evidence_quotes": []
        }

    def get_session_profile(self, session_id: str) -> Dict:
        """Get current profile for verdict service."""
        self._ensure_session(session_id)
        analyzer = self._get_analyzer(session_id)
        return analyzer.get_profile_snapshot()

    def get_search_profile(self, session_id: str) -> Dict:
        """Get profile optimized for search queries."""
        self._ensure_session(session_id)
        analyzer = self._get_analyzer(session_id)
        return analyzer.get_search_profile()

    def cleanup_session(self, session_id: str):
        """Remove analyzer and tracking data when session complete."""
        self._ensure_session(session_id)
        self._analyzers.pop(session_id, None)
        self._question_history.pop(session_id, None)
        self._used_vectors.pop(session_id, None)
        self._topic_categories.pop(session_id, None)
        self._invalidated_vectors.pop(session_id, None)
        self._locked_vectors.pop(session_id, None)
        self._session_modes.pop(session_id, None)
        self._insights_sent.pop(session_id, None)
        self._hypotheses.pop(session_id, None)
        self._min_questions.pop(session_id, None)
        self._low_info_streaks.pop(session_id, None)
        self._signal_progress.pop(session_id, None)
        self._clue_usage.pop(session_id, None)
        self._last_reason_to_continue.pop(session_id, None)

    def _parse_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from LLM response."""
        if not text:
            return None

        # Strip markdown code blocks first
        clean = re.sub(r'```(?:json|JSON)?\s*\n?', '', text)
        clean = re.sub(r'\n?\s*```', '', clean)
        clean = clean.strip()

        # Step 2: Fix double-brace escaping (if any leakage)
        if '{{' in clean and '{{{' not in clean:
            clean = clean.replace('{{', '{').replace('}}', '}')

        # Direct parse
        try:
            return json.loads(clean)
        except (json.JSONDecodeError, TypeError):
            pass

        # Find JSON object with nested braces (fallback)
        match = re.search(
            r'\{[^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*\}',
            text, re.DOTALL
        )
        if match:
            try:
                candidate = match.group(0)
                # Cleaning candidate just in case
                candidate = re.sub(r'```(?:json|JSON)?\s*\n?', '', candidate)
                candidate = re.sub(r'\n?\s*```', '', candidate)
                return json.loads(candidate)
            except (json.JSONDecodeError, TypeError):
                pass

        logger.warning(f"[INTERROGATION] JSON parse failed: {text[:200]}...")
        return None


# Global instance
interrogation_service = InterrogationService(api_client)
