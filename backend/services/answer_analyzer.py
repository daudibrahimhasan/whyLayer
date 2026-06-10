"""
Answer Analyzer v3 — LLM-Powered Psychology Extraction
Detects Script/Fog/Nerve layers. Uses Groq for speed.
"""

import json
import logging
import re
from typing import Optional, Dict, List, Any

from services.llm_service import api_client

logger = logging.getLogger(__name__)

# ─── Analysis Prompt ──────────────────────────────────────────────────────────

ANALYSIS_PROMPT = """You are analyzing a subject's response to extract psychological data for weaponization.

THE THREE LAYERS:
- SCRIPT: Rehearsed, logical, performance. They want validation, not a decision.
- FOG: ANY admission of emotion (sadness, worry), doubt, or difficulty. If they stop performing and start feeling, it is FOG.
- NERVE: Raw reaction. Defensive anger, sudden silence, subject change. You hit it.

DECISION CONTEXT:
"{query}"

CURRENT QUESTION:
"{question}"

SUBJECT'S ANSWER:
"{answer}"

EXISTING PROFILE:
{existing_profile}

CONVERSATION HISTORY:
{conversation_history}

═══════════════════════════════════════════════════
ANALYZE FOR WEAPONIZATION:

1. LAYER DETECTION — Which layer is this answer from?

2. WEAPONIZABLE PHRASES — Extract exact words to use against them:
   - Words that reveal their real priority ("stable" = they value safety, attack the safety)
   - Qualifiers that betray doubt ("I think I could" = they don't believe themselves)
   - Rehearsed phrases ("figure it out" = no plan, just prayer)
   - Words they repeated = what's consuming them

3. EVASION DETECTION:
   - deflection: Answered different question
   - humor: Jokes to avoid discomfort  
   - vagueness: Abstract, non-specific
   - aggression: Attacking the question
   - none: Honest

4. PSYCHOLOGICAL SIGNALS from their EXACT WORDS:
   - Stated reason (what they claim)
   - Hidden fear (what they're running from)
   - Target person (who they're performing for)
   - Root insecurity (what they believe about themselves)
   - Competence gap (what they can't do)

5. ATTACK VECTOR — Which would hurt most?
   - vanity: Cares about perception
   - fear: Running from something
   - competence: Can't actually do this
   - insecurity: Deep inadequacy belief

6. CONFIDENCE (0-100):
   - 0-20: Script only
   - 20-40: Some fog
   - 40-60: Contradictions exposed
   - 60-80: Nerve identified
   - 80-100: Full map

CRITICAL NULL RULE:
If no clear psychological signal exists in the answer, return null for that field.
Do NOT infer hidden fears, insecurities, or motivations that aren't evidenced by their EXACT words.
A short or simple answer doesn't mean they're hiding something — it might just be a short answer.
Better to return null than to fabricate insight. Accuracy > depth.

Respond ONLY with this JSON:
{{
    "current_layer": "script|fog|nerve",
    "stated_reason": "what they claim, using THEIR words" or null,
    "hidden_fear": "what they're actually afraid of (inferred)" or null,
    "real_motivation": "what's actually driving them" or null,
    "target_person": "who they're trying to impress/escape" or null,
    "core_fear": "deepest fear detected" or null,
    "competence_gap": "skill/experience they lack" or null,
    "root_insecurity": "fundamental belief about their inadequacy" or null,
    "core_delusion": "false belief they hold about reality" or null,
    "evasion_detected": true/false,
    "evasion_type": "deflection|humor|vagueness|aggression|none",
    "emotional_state": "defensive|anxious|confident|confused|honest|evasive|angry",
    "key_phrases": ["exact quotes that reveal something"],
    "contradictions_found": ["specific contradictions between this and previous answers"],
    "new_weaknesses": [
        {{"type": "vanity|fear|competence|insecurity", "detail": "specific finding", "severity": 1-10}}
    ],
    "exposure_confidence": 0-100,
    "what_to_probe_next": "specific angle based on what they revealed or avoided",
    "nerve_hypothesis": "your current theory about their core wound" or null,
    "internal_deduction": "private running deduction for later use only" or null,
    "weaponizable_phrases": ["exact quotes from the subject's answer"]
}}

CRITICAL: If no contradictions exist between this answer and previous answers,
return an EMPTY list []. Do NOT fabricate or infer contradictions that aren't
directly evidenced by the user's EXACT words. Only flag contradictions where
the user literally said X before and now says not-X.
═══════════════════════════════════════════════════"""

# ─── Compressed Analysis Prompt (used after first call) ───────────────────────

ANALYSIS_PROMPT_SHORT = """Analyze this response for the ongoing psychological profile.

DECISION: "{query}"
QUESTION: "{question}"
ANSWER: "{answer}"
EXISTING PROFILE: {existing_profile}
CONVERSATION: {conversation_history}

Extract: layer (script/fog/nerve), evasion, weaponizable phrases, contradictions with EXACT previous words only.

CRITICAL: If no contradictions exist, return an EMPTY list []. Do NOT fabricate.

Respond ONLY with JSON:
{{
    "current_layer": "script|fog|nerve",
    "stated_reason": "what they claim" or null,
    "hidden_fear": "what they're afraid of" or null,
    "real_motivation": "what's driving them" or null,
    "target_person": "who they're performing for" or null,
    "core_fear": "deepest fear" or null,
    "competence_gap": "skill/experience gap" or null,
    "root_insecurity": "fundamental inadequacy belief" or null,
    "core_delusion": "false belief" or null,
    "evasion_detected": true/false,
    "evasion_type": "deflection|humor|vagueness|aggression|none",
    "emotional_state": "defensive|anxious|confident|confused|honest|evasive|angry",
    "key_phrases": ["exact quotes that reveal something"],
    "contradictions_found": [],
    "new_weaknesses": [
        {{"type": "vanity|fear|competence|insecurity", "detail": "finding", "severity": 1-10}}
    ],
    "exposure_confidence": 0-100,
    "what_to_probe_next": "specific angle",
    "nerve_hypothesis": "core wound theory" or null,
    "internal_deduction": "private running deduction for later use only" or null,
    "weaponizable_phrases": ["exact quotes from the subject's answer"]
}}
"""


class AnswerAnalyzer:
    """LLM-powered psychology extraction with Script/Fog/Nerve detection."""

    # Words that look like answers but say nothing
    NON_ANSWERS = {
        "both", "neither", "idk", "maybe", "sure", "yes", "no",
        "i guess", "probably", "kind of", "sort of", "whatever",
        "i don't know", "not sure", "depends", "none", "all",
        "everything", "nothing", "same", "ok", "okay", "fine"
    }

    def __init__(self, llm_service=None):
        self.llm = llm_service if llm_service else api_client
        self.profile_data = {}
        self.all_weaknesses = []
        self.vectors_used = set()
        self.confidence = 0
        self.probe_suggestion = None
        self.nerve_hypothesis = None
        self.contradictions = []
        self.previous_answers = []  # Track for repetition detection
        self.call_count = 0         # Track calls for prompt compression
        self.answer_lengths = []    # Track word counts for behavioral analysis
        self.weaponizable_phrases = [] # Track exact quotes to use against them
        self.internal_deductions = []
        self.weakness_summary = []
        self.consecutive_evasions = 0

    def detect_evasion(self, answer: str, question: str, history: List[Dict], response_type: str = "question") -> Dict:
        """Detect HOW the user is avoiding the question."""
        clean = answer.strip().lower().rstrip(".!?,")
        words = clean.split()
        word_count = len(words)

        # Observations and mirrors naturally get shorter responses
        # e.g., "You're waiting for her." -> "Maybe." (This is valid, not evasion)
        is_observation = response_type in ("observation", "mirror")

        # 1. Single word — Check context
        if word_count == 1:
            if clean in self.NON_ANSWERS:
                return {
                    "type": "low_signal",
                    "severity": "low",
                    "response": (
                        f'"{answer}" is not an answer. It\'s a reflex. '
                        f'The question had weight. Your answer didn\'t. Try again.'
                    ),
                }
            
            # If it's an observation, a single word confirmation/denial is allowed
            if is_observation:
                return None  # Valid response to observation

            # Even a "real" word is still low signal for a direct QUESTION
            return {
                    "type": "low_signal",
                    "severity": "low",
                    "response": (
                        f'"{answer}." One word. For a question about your life. '
                        f'Either you\'ve already decided and you\'re performing indecision, '
                        f'or you\'re afraid of what a full answer reveals.'
                    ),
                }

        # 2. Two words — still suspicious for questions, okay for observations
        if word_count == 2:
            if is_observation:
                return None # Valid response to observation

            if clean in self.NON_ANSWERS:
                return {
                    "type": "low_signal",
                    "severity": "low",
                    "response": (
                        f'"{answer}" — that\'s not a thought. '
                        f'That\'s a placeholder where a thought should be.'
                    ),
                }

        # 3. Echo detection — did they just repeat part of the question?
        question_words = set(question.lower().split())
        answer_words = set(words)
        if word_count <= 3 and answer_words.issubset(question_words):
            return {
                "type": "echo",
                "severity": "medium",
                "response": (
                    'You just echoed my question back at me. '
                    'That\'s not answering. That\'s stalling.'
                ),
            }

        # 4. Repeated answer detection
        repeat_count = sum(1 for a in self.previous_answers if a.strip().lower() == clean)
        if repeat_count >= 1:
            return {
                "type": "repetition",
                "severity": "high",
                "count": repeat_count + 1,
                "response": (
                    f'You\'ve said "{answer}" {repeat_count + 1} times now. '
                    f'Repetition isn\'t conviction. It\'s a script. '
                    f'Say something you haven\'t rehearsed.'
                ),
            }

        # Track this answer for future repetition checks
        self.previous_answers.append(clean)

        # 5. Confusion detection — user doesn't understand the question
        confusion_phrases = [
            "what kind of question", "what do you mean", "i don't understand",
            "what are you asking", "that doesn't make sense", "huh",
            "what does that mean", "can you rephrase", "i'm confused",
            "that's a weird question", "what",
        ]
        if any(phrase in clean for phrase in confusion_phrases):
            return {
                "type": "confusion",
                "severity": "none",  # Not evasion — genuine confusion
                "response": None,    # Don't call them out, switch vector instead
            }

        return {"type": "none", "severity": "none", "response": None}


    async def analyze(
        self,
        query: str,
        question: str,
        answer: str,
        history: List[Dict],
        existing_profile: Optional[Dict] = None,
    ) -> Dict:
        """Analyze a single answer and update the running profile."""

        # Format conversation history
        conv_lines = []
        for h in history:
            q = h.get("question", h.get("text", ""))
            a = h.get("answer", "")
            conv_lines.append(f"Q: {q}")
            conv_lines.append(f"A: {a}")
        conversation_str = "\n".join(conv_lines) if conv_lines else "(first answer)"

        # Format existing profile
        profile_to_use = existing_profile if existing_profile else self.profile_data
        profile_str = json.dumps(profile_to_use, indent=2, default=str) if profile_to_use else "(empty)"

        # Track answer length for behavioral observations
        self.answer_lengths.append(len(answer.split()))
        self.call_count += 1

        # Use compressed prompt after first call (saves ~400 tokens)
        prompt_template = ANALYSIS_PROMPT if self.call_count <= 1 else ANALYSIS_PROMPT_SHORT
        prompt = prompt_template.format(
            query=query,
            question=question,
            answer=answer,
            existing_profile=profile_str,
            conversation_history=conversation_str,
        )

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.llm.call_with_fallback(
                messages=messages,
                temperature=0.3,
                prefer_groq=True,
            )

            analysis = self._parse_response(response)

            if analysis:
                # Rule override for specific raw fear signals that the LLM misreads as vagueness
                ans_clean = answer.strip().lower().rstrip(".!?,")
                if ans_clean in ["no response", "they might ignore", "ignored"]:
                    analysis["evasion_detected"] = False
                    analysis["evasion_type"] = "none"
                    analysis["hidden_fear"] = "fear of rejection or irrelevance"
                    analysis["emotional_state"] = "fear"
                    analysis["current_layer"] = "nerve"

                self._update_profile(analysis)
                logger.info(
                    f"[ANALYZER] Layer: {analysis.get('current_layer', '?')} | "
                    f"Confidence: {self.confidence}% | "
                    f"Evasion: {analysis.get('evasion_type', 'none')} | "
                    f"Probe: {self.probe_suggestion}"
                )
                return analysis

        except Exception as e:
            logger.error(f"[ANALYZER] LLM analysis failed: {e}")

        # Minimal fallback — still dynamic
        return self._fallback_analysis(answer)

    def _parse_response(self, response: str) -> Optional[Dict]:
        """Extract JSON from LLM response."""
        if not response:
            return None

        # Step 1: Strip markdown code blocks
        clean = re.sub(r'```(?:json|JSON)?\s*\n?', '', response)
        clean = re.sub(r'\n?\s*```', '', clean)
        clean = clean.strip()

        # Step 2: Fix double-brace escaping from f-string contamination
        if '{{' in clean and '{{{' not in clean:
            clean = clean.replace('{{', '{').replace('}}', '}')

        # Step 3: Try direct parse
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            pass

        # Step 4: Find JSON object boundaries
        start = clean.find('{')
        end = clean.rfind('}') + 1
        if start != -1 and end > start:
            try:
                return json.loads(clean[start:end])
            except json.JSONDecodeError:
                pass

        # Step 5: Try nested object regex
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning(f"[ANALYZER] JSON parse failed: {response[:200]}...")
        return None

    def _update_profile(self, analysis: Dict):
        """Merge analysis into running profile."""

        # FIX 3: NULL GATE — Ignore low-confidence psychological signals
        # If confidence is very low, the LLM is guessing. Don't store guesses.
        raw_confidence = analysis.get("exposure_confidence", 0)
        is_low_confidence = isinstance(raw_confidence, (int, float)) and raw_confidence < 30

        self._signal_counts = getattr(self, "_signal_counts", {})

        def _promote_signal(field: str, value):
            if not value:
                return

            v = str(value).strip()
            if not v or v.lower() in ("null", "none", ""):
                return

            self._signal_counts.setdefault(field, {})
            self._signal_counts[field][v] = self._signal_counts[field].get(v, 0) + 1
            count = self._signal_counts[field][v]
            confidence = analysis.get("exposure_confidence", 0)

            if field not in self.profile_data:
                if field in {"stated_reason"}:
                    self.profile_data[field] = v
                elif confidence >= 45 or count >= 2:
                    self.profile_data[field] = v
            else:
                if confidence >= 45 or count >= 2:
                    self.profile_data[field] = v

        layer = analysis.get("current_layer")
        if layer and str(layer).lower() not in ("null", "none", ""):
            self.profile_data["current_layer"] = layer

        # Update profile fields
        profile_fields = [
            "stated_reason", "hidden_fear", "real_motivation", "target_person",
            "core_fear", "competence_gap", "root_insecurity", "core_delusion",
            "nerve_hypothesis",
        ]

        # FIX 3: Deep psychology fields that should be GATED when confidence is low
        gated_fields = {"hidden_fear", "core_fear", "root_insecurity", "core_delusion", "nerve_hypothesis"}

        for field in profile_fields:
            value = analysis.get(field); _promote_signal(field, value)
            if value and str(value).lower() not in ("null", "none", ""):
                # FIX 3: Skip deep psychology fields when confidence is too low
                if is_low_confidence and field in gated_fields:
                    print(f"[ANALYZER] FIX 3: NULL GATE — Ignoring '{field}' at confidence {raw_confidence}%")
                    continue
                self.profile_data[field] = value

        # Track nerve hypothesis
        nerve = self.profile_data.get("nerve_hypothesis")
        if nerve and str(nerve).lower() not in ("null", "none", ""):
            if nerve != self.nerve_hypothesis:
                print(f"[ANALYZER] !!! NEW NERVE HYPOTHESIS: {nerve}")
            self.nerve_hypothesis = nerve

        # Accumulate contradictions — VALIDATE quotes against actual history
        new_contradictions = analysis.get("contradictions_found", [])
        if new_contradictions:
            validated = []
            for c in new_contradictions:
                c_str = str(c).lower()
                # Check if any quoted word cluster actually appears in user's previous answers
                is_real = False
                for prev in self.previous_answers:
                    # Check for ≥3 word overlap from the contradiction claim
                    c_words = set(c_str.split())
                    prev_words = set(prev.split())
                    overlap = c_words & prev_words
                    if len(overlap) >= 3:
                        is_real = True
                        break
                if is_real:
                    print(f"[ANALYZER] !!! CONTRADICTION VALIDATED: {c}")
                    validated.append(c)
                else:
                    print(f"[ANALYZER] Rejected hallucinated contradiction: {c}")
            if validated:
                self.contradictions.extend(validated)
                self.profile_data["contradictions"] = self.contradictions[-10:]

        # Accumulate weaknesses
        new_weaknesses = analysis.get("new_weaknesses", [])
        for w in new_weaknesses:
            if isinstance(w, dict) and w.get("detail"):
                self.all_weaknesses.append(w)
                if w.get("type"):
                    self.vectors_used.add(w["type"])

        internal_deduction = analysis.get("internal_deduction")
        if internal_deduction and str(internal_deduction).lower() not in ("null", "none", ""):
            self.internal_deductions.append(str(internal_deduction))
            self.internal_deductions = self.internal_deductions[-6:]

        # Capture weaponizable phrases
        new_weapons = analysis.get("weaponizable_phrases", [])
        if new_weapons:
            # Validate they appear in recent answer if possible, but trust the extraction logic for now
            # Filter for meaningful length to avoid junk
            valid_weapons = [w for w in new_weapons if isinstance(w, str) and len(w) > 3]
            self.weaponizable_phrases.extend(valid_weapons)
            self.weaponizable_phrases = self.weaponizable_phrases[-12:]

        # Update confidence — TIERED by answer quality + emotional content
        new_confidence = analysis.get("exposure_confidence", 0)
        if isinstance(new_confidence, (int, float)):
            evasion = analysis.get("evasion_detected", False)
            evasion_type = analysis.get("evasion_type", "none")
            layer = analysis.get("current_layer", "script")
            emotional_state = analysis.get("emotional_state", "unknown")
            is_short = len(self.answer_lengths) > 0 and self.answer_lengths[-1] <= 3
            last_answer_len = self.answer_lengths[-1] if self.answer_lengths else 0

            # Emotional keyword detection in the answer itself
            # (answer_lengths tracks the last answer's word count,
            #  but we need the actual text — use profile data instead)
            EMOTIONAL_STATES = {"anxious", "defensive", "angry", "honest", "sad", "relieved"} # Confused removed
            NERVE_STATES = {"angry", "defensive", "broken"}

            if evasion or (evasion_type not in ("none", None) and evasion_type != "confusion") or is_short:
                max_bump = 5   # Evasive answers reveal little
            elif emotional_state == "confused":
                max_bump = 5   # Confusion means we missed the mark or they're lost. Low confidence.
            elif layer == "nerve" or emotional_state in NERVE_STATES:
                max_bump = 25  # Nerve-level: anger, tears, silence = jackpot
            elif layer == "fog" or emotional_state in EMOTIONAL_STATES:
                max_bump = 15  # Fog/emotional: sadness, anxiety, honesty
            elif last_answer_len >= 15:
                max_bump = 12  # Detailed answer — reveals structure
            else:
                max_bump = 10  # Standard answer
            
            # CRITICAL: Bonus for nerve identification
            if self.nerve_hypothesis and self.nerve_hypothesis not in ("neither", "none", None):
                 # If we have a hypothesis, we are much closer to the truth
                 max_bump += 20 

            raw_bump = max(5, int(new_confidence) - self.confidence)
            bump = min(max_bump, raw_bump)
            self.confidence = min(100, self.confidence + bump)
            print(f"[ANALYZER] Confidence: {self.confidence}% (+{bump}, cap={max_bump}, layer={layer})")

        # Store probe suggestion
        self.probe_suggestion = analysis.get("what_to_probe_next")

        # Store emotional state and evasion
        self.profile_data["emotional_state"] = analysis.get("emotional_state", "unknown")
        self.profile_data["evasion_detected"] = analysis.get("evasion_detected", False)
        self.profile_data["evasion_type"] = analysis.get("evasion_type", "none")
        self.profile_data["current_layer"] = analysis.get("current_layer", "script")

        if analysis.get("evasion_detected") and analysis.get("evasion_type") not in ("none", "confusion", None):
            self.consecutive_evasions += 1
        else:
            self.consecutive_evasions = 0

        # Accumulate key phrases
        key_phrases = self.profile_data.get("key_phrases", [])
        new_phrases = analysis.get("key_phrases", [])
        if new_phrases:
            key_phrases.extend(new_phrases)
            self.profile_data["key_phrases"] = key_phrases[-20:]

        self.weakness_summary = self._build_weakness_summary()

    def _fallback_analysis(self, answer: str) -> Dict:
        """Minimal fallback when LLM fails — still context-aware."""
        answer_lower = answer.lower().strip()

        # Detect evasion patterns
        is_short = len(answer_lower) < 15
        is_dismissive = answer_lower in ["idk", "i don't know", "maybe", "not sure", "whatever", "none", "no", "yes"]

        evasion = is_short or is_dismissive
        
        # Small confidence bump for any response
        self.confidence = max(self.confidence, min(self.confidence + 3, 100))

        # Dynamic probe based on evasion
        if is_dismissive:
            probe = "They're refusing to engage. Push harder on what they're avoiding."
        elif is_short:
            probe = "Short answer suggests discomfort. Find what makes them uncomfortable."
        else:
            probe = "Continue probing for contradictions or emotional triggers."

        self.probe_suggestion = probe

        return {
            "current_layer": "script",
            "evasion_detected": evasion,
            "evasion_type": "vagueness" if evasion else "none",
            "emotional_state": "evasive" if evasion else "unknown",
            "exposure_confidence": self.confidence,
            "new_weaknesses": [],
            "what_to_probe_next": probe,
        }

    def _build_weakness_summary(self) -> List[str]:
        summary = []
        if self.profile_data.get("hidden_fear") or self.profile_data.get("core_fear"):
            summary.append(f"Known fear: {self.profile_data.get('hidden_fear') or self.profile_data.get('core_fear')}")
        if self.contradictions:
            summary.append(f"Contradiction logged: {self.contradictions[-1]}")
        if self.profile_data.get("evasion_type") not in ("none", None):
            summary.append(f"Behavioral tell: {self.profile_data.get('evasion_type')}")
        if self.profile_data.get("root_insecurity"):
            summary.append(f"Root insecurity: {self.profile_data.get('root_insecurity')}")
        if self.profile_data.get("competence_gap"):
            summary.append(f"Competence gap: {self.profile_data.get('competence_gap')}")
        if self.internal_deductions:
            summary.append(f"Private read: {self.internal_deductions[-1]}")
        return summary[-4:]

    def get_profile_snapshot(self) -> Dict:
        """Return current profile for use in prompts."""
        return {
            "profile": self.profile_data,
            "weaknesses": self.all_weaknesses,
            "vectors_used": list(self.vectors_used),
            "confidence": self.confidence,
            "probe_suggestion": self.probe_suggestion,
            "nerve_hypothesis": self.nerve_hypothesis,
            "contradictions": self.contradictions,
            "answer_length_trend": self.answer_lengths,
            "weaponizable_phrases": self.weaponizable_phrases,
            "internal_deductions": self.internal_deductions,
            "weakness_summary": self.weakness_summary,
            "consecutive_evasions": self.consecutive_evasions,
        }

    def get_search_profile(self) -> Dict:
        """Return profile optimized for search query generation."""
        return {
            "target_person": self.profile_data.get("target_person"),
            "core_fear": self.profile_data.get("core_fear"),
            "hidden_fear": self.profile_data.get("hidden_fear"),
            "competence_gap": self.profile_data.get("competence_gap"),
            "root_insecurity": self.profile_data.get("root_insecurity"),
            "real_motivation": self.profile_data.get("real_motivation"),
            "nerve_hypothesis": self.nerve_hypothesis,
            "key_phrases": self.profile_data.get("key_phrases", []),
            "weakness_summary": self.weakness_summary,
        }
