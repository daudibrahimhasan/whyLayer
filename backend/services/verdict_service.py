# services/verdict_service.py
import re
"""
Final verdict synthesis service.
Combines psychology profile with web research to generate verdict.
"""

from typing import Dict, List, Optional

from schemas.psychology_profile import PsychologyProfile, DecisionType
from prompts.verdict import build_verdict_prompt
from .llm_service import api_client, _extract_json_object, ContextManager
from .evidence_hunter import EvidenceHunter, evidence_hunter
from .user_profile_service import update_user_profile, detect_repetition, get_escalation_level, get_user


class VerdictService:
    """
    Generates final verdicts by combining:
    1. Psychology profile from interrogation
    2. Web research from evidence hunting
    3. LLM synthesis
    """
    
    def __init__(self, hunter: EvidenceHunter = None, db=None):
        self.hunter = hunter or evidence_hunter
        self.db = db

    def _detect_personality(self, profile) -> str:
        """Categorize user based on psychological markers."""
        if profile.root_insecurity:
            return "The Imposter"
        if profile.hidden_fear:
            return "The Avoider"
        if profile.competence_gap:
            return "The Dreamer"
        return "The Drifter"

    def _apply_adaptive_tone(self, summary: str, decision: str, profile, user_id: str = "default_user") -> str:
        text = summary.strip().lower()

        # Load escalation level
        level = get_escalation_level(user_id)

        vector = profile.vectors_used[-1].value.lower() if getattr(profile, "vectors_used", None) else None

        if vector in ["nerve", "insecurity", "competence", "fear"]:
            mode = vector
        elif profile.nerve_hypothesis:
            mode = "nerve"
        elif profile.root_insecurity:
            mode = "insecurity"
        elif profile.competence_gap:
            mode = "competence"
        elif getattr(profile, "hidden_fear", None) or getattr(profile, "core_fear", None):
            mode = "fear"
        else:
            mode = "default"

        # --- Tone transformations ---
        if mode == "fear":
            line = "You’re not confused. You’re avoiding what happens if this goes wrong."

        elif mode == "insecurity":
            line = "This isn’t about the decision. It’s about what it says about you."

        elif mode == "competence":
            line = "You’re treating this like a choice. It’s a capability problem."

        elif mode == "nerve":
            line = f"You already said it yourself: {profile.nerve_hypothesis}"

        else:
            line = "You already know the answer. You’re delaying saying it."

        # Clean weak language
        replacements = {
            "maybe": "",
            "might": "",
            "could": "",
            "possibly": "",
            "it seems": "",
            "there are risks": "You already know this is risky",
        }

        for k, v in replacements.items():
            text = text.replace(k, v)

        # Rebuild
        final = f"{line}\n\n{text}"

        # Add escalation layer
        if level == 2:
            final += "\n\nYou’ve been here before. Nothing changed."
        elif level == 3:
            final += "\n\nAt this point, you're not stuck. You're choosing this."

        # Add decisive ending
        if decision == "GO":
            final += "\n\nYou’re going to do it anyway. At least be honest about that."
        else:
            final += "\n\nYou already know this is a bad idea. You’re just hoping I’ll say otherwise."

        if profile.weaponizable_phrases:
            phrase = profile.weaponizable_phrases[0]
            final = f'You said "{phrase}". That’s all I needed.\n\n{final}'

        return final

    def _adaptive_truth(self, truth: str, profile) -> str:
        base = truth or ""

        if profile.root_insecurity:
            return f"You’re protecting your self-image, not making a decision. {base}"

        if profile.hidden_fear:
            return f"This isn’t about the choice. It’s about avoiding {profile.hidden_fear}. {base}"

        if profile.competence_gap:
            return f"You don’t lack options. You lack the ability to execute. {base}"

        return base or "You’re not being honest about what you actually want."

    def generate(
        self,
        query: str,
        profile: PsychologyProfile,
        history: List[Dict],
        user_id: str = "default_user",
        skip_search: bool = False,
        research_override: Optional[Dict] = None
    ) -> Dict:
        """
        Generate final verdict with all components.
        """
        print(f"[VERDICT] Generating verdict for: {query[:50]}...")
        
        # Step 1: Use provided research or skip
        web_research = {}
        if research_override:
            print(f"[VERDICT] Using provided research ({len(research_override.get('sources', []))} sources)")
            web_research = research_override
        else:
            print("[VERDICT] No research provided, verdict based on interrogation only")
            web_research = self._empty_web_research()

        
        # Step 2: Load user memory & Detect persistent markers
        user_memory = get_user(user_id)
        repeat_pattern = detect_repetition(user_id)
        level = get_escalation_level(user_id)
        
        # Inject memory into profile context before building prompt (Influence Logic)
        if user_memory.get("total_sessions", 0) > 0:
            profile.root_insecurity = profile.root_insecurity or user_memory.get("dominant_pattern")
            profile.nerve_hypothesis = profile.nerve_hypothesis or user_memory.get("dominant_vector")
            
        # FIX 3 — Inject stored weapon phrases into current profile
        stored_weapons = user_memory.get("weaponizable_phrases", [])
        if stored_weapons:
            profile.weaponizable_phrases = (
                stored_weapons[:2] + (profile.weaponizable_phrases or [])
            )

        # Step 3: Build conversation summary
        conversation_summary = ContextManager.compress_history(history, max_pairs=5)
        
        # Step 4: Build web research summary for LLM
        web_summary = self._summarize_web_research(web_research)
        
        # Step 5: Calculate confidence from profile
        confidence = profile.calculate_exposure_confidence()
        
        # Step 6: Build verdict prompt
        prompt = build_verdict_prompt(
            query=query,
            decision_type=profile.decision_type.value,
            conversation_summary=conversation_summary,
            profile={
                "stated_reason": profile.stated_reason,
                "real_motivation": profile.real_motivation,
                "hidden_fear": profile.hidden_fear or profile.core_fear,
                "core_delusion": profile.core_delusion,
                "target_person": profile.target_person,
                "root_insecurity": profile.root_insecurity,
                "competence_gap": profile.competence_gap,
                "nerve_hypothesis": profile.nerve_hypothesis,
                "weaponizable_phrases": profile.weaponizable_phrases,
            },
            web_research_summary=web_summary,
            confidence=confidence,
            options=profile.options if profile.decision_type == DecisionType.MULTI_OPTION else None,
            memory_context={
                "past_pattern": user_memory.get("dominant_pattern"),
                "dominant_trait": user_memory.get("dominant_vector"),
                "sessions": user_memory.get("total_sessions")
            }
        )
        
        # FIX 4 — Active Pattern Attack Injection
        if repeat_pattern:
            prompt += f"\n\nREPEATED BEHAVIOR DETECTED:\nUser consistently shows this pattern: {repeat_pattern}\n\nInstruction:\n- Call this out directly\n- Do NOT soften it\n- Make it clear this is a repeated avoidance loop"

        # Escalation level injection
        if level >= 2:
            prompt += "\n\nCRITICAL: User has repeated avoidance behavior. Increase bluntness and psychological pressure."

        messages = [{"role": "user", "content": prompt}]
        
        # Step 7: Generate verdict via LLM with fallback chain (FIX 5 + FIX 9)
        try:
            print(f"[VERDICT] Calling LLM with prompt length: {len(prompt)} chars")
            print(f"[VERDICT] Calling LLM with fallback chain for verdict...")

            # Use the public fallback method instead of calling private _call_gemini directly
            response = api_client.call_with_fallback(
                messages, prefer_gemini=True, temperature=0.3, max_tokens=2000
            )
            verdict_data = _extract_json_object(response)

            if not verdict_data:
                print("[VERDICT] Gemini failed to return valid JSON payload")
                return self._fallback_verdict(profile, web_research, history)

            # FIX 5: REMOVED double-pass (Gemini analysis → Grok decision)
            # The single Gemini call now handles both analysis and decision.
            # This saves 1 full LLM call per verdict (was: 3 calls, now: 1 call)

            # Form the verdict
            verdict = self._format_verdict(verdict_data, profile, web_research, history, user_id=user_id)
            
            # PERSISTENCE - Update user patterns after completion
            update_user_profile(user_id, profile, verdict_data)
            
            if repeat_pattern:
                verdict["pattern_detected"] = True
                verdict["pattern_message"] = f"You keep repeating this pattern: {repeat_pattern}."
                # We don't append to summary here because it's now INJECTED into the prompt response itself
            
            return verdict
        
        except Exception as e:
            print(f"[VERDICT] LLM verdict generation failed: {e}")
            import traceback
            traceback.print_exc()
        
        # Fallback verdict - try to use at least the web research
        print("[VERDICT] Using fallback verdict mechanism")
        return self._fallback_verdict(profile, web_research, history)
    
    def _summarize_web_research(self, research: Dict) -> str:
        """
        Summarize web research for LLM prompt.
        """
        if not research.get("sources"):
            return "No web research available. Base verdict on interrogation data only."
        
        lines = []
        
        if research.get("sentiment_summary"):
            lines.append(f"OVERALL SENTIMENT: {research['sentiment_summary']}")
        
        if research.get("typical_outcomes", {}).get("negative"):
            lines.append("COMMON REGRETS:")
            for regret in research["typical_outcomes"]["negative"][:3]:
                lines.append(f"  - {regret[:100]}...")
        
        if research.get("typical_outcomes", {}).get("positive"):
            lines.append("SUCCESS STORIES:")
            for success in research["typical_outcomes"]["positive"][:2]:
                lines.append(f"  - {success[:100]}...")
        
        if research.get("warning_signs"):
            lines.append("WARNING SIGNS OTHERS MENTIONED:")
            for warning in research["warning_signs"][:3]:
                lines.append(f"  - {warning[:100]}...")

        if research.get("fact_bludgeons"):
            lines.append("CACHED FACTS:")
            for fact in research["fact_bludgeons"][:4]:
                lines.append(f"  - {fact[:120]}")
        
        summary_text = "\n".join(lines) if lines else "Limited web research available."
        
        print("\n═══════════════════════════════════════════════════════════════════════════════")
        print("🌐 WEB RESEARCH INJECTED INTO VERDICT PROMPT:")
        print(summary_text)
        print("═══════════════════════════════════════════════════════════════════════════════\n")
        
        return summary_text
    
    def _format_verdict(
        self,
        verdict_data: dict,
        profile: PsychologyProfile,
        web_research: dict,
        history: list,
        user_id: str = "default_user"
    ) -> dict:
        """
        Format LLM response into complete verdict structure.
        """
        import re
        summary_raw = verdict_data.get("summary", "Analysis complete.")
        match = re.search(r"final decision:\s*(yes|no|go|no-go)", summary_raw.lower())
        
        if match:
            decision_val = match.group(1).upper()
            if decision_val in ["YES", "GO"]:
                status = "GO"
            else:
                status = "NO-GO"
        else:
            status = "NO-GO"

        exposure = verdict_data.get("psychology_exposure", {})
        psychology_exposure = {
            "stated_want": exposure.get("stated_want") or profile.stated_reason,
            "real_want": exposure.get("real_want") or profile.real_motivation,
            "hidden_fear": exposure.get("hidden_fear") or profile.hidden_fear or profile.core_fear,
            "core_delusion": exposure.get("core_delusion") or profile.core_delusion,
            "attack_that_worked": exposure.get("attack_that_worked") or (
                profile.vectors_used[-1].value if profile.vectors_used else None
            ),
        }
        
        receipt = []
        if profile.weaponizable_phrases:
            for phrase in profile.weaponizable_phrases[:2]:
                receipt.append({
                    "you_said": phrase,
                    "reality": verdict_data.get("the_truth", "")
                })

        def _ensure_attack_line(summ: str) -> str:
            if not any(w in summ.lower() for w in ["you", "you're", "you’re"]):
                return "You’re not unsure. You’re avoiding a decision.\n\n" + summ
            return summ

        raw_summary = verdict_data.get("summary", "Analysis complete.")
        summary = _ensure_attack_line(raw_summary)
        summary = self._apply_adaptive_tone(summary, status, profile, user_id=user_id)

        personality = self._detect_personality(profile)
        
        verdict = {
            "status": status,
            "confidence": max(0, min(100, verdict_data.get("confidence", profile.exposure_confidence))),
            "summary": summary,
            "personality_type": personality,
            "personality_summary": f"{personality}: You repeat the same pattern under pressure.",
            "the_truth": self._adaptive_truth(verdict_data.get("the_truth", ""), profile),
            "rationales": verdict_data.get("rationales", ["Analysis completed"]),
            "risks": verdict_data.get("risks", []),
            "deal_breakers": verdict_data.get("deal_breakers", []),
            "success_probability": verdict_data.get("success_probability", "Unknown"),
            "key_advice": verdict_data.get("key_advice", []),
            "required_actions": verdict_data.get("required_actions", []),
            "receipt": receipt,
            "nerve_hit": bool(profile.nerve_hypothesis),
            "nerve_message": "⚠️ You reacted differently when this came up." if profile.nerve_hypothesis else None,
            "psychology_exposure": psychology_exposure,
            "community_sentiment": web_research.get("sentiment_summary", "Neutral"),
            "web_research": {
                "common_experiences": web_research.get("common_experiences", []),
                "typical_outcomes": web_research.get("typical_outcomes", {"positive": [], "negative": []}),
                "community_advice": web_research.get("community_advice", []),
                "warning_signs": web_research.get("warning_signs", []),
                "success_patterns": web_research.get("success_patterns", []),
                "failure_patterns": web_research.get("failure_patterns", []),
                "sentiment_summary": web_research.get("sentiment_summary", ""),
                "sources": web_research.get("sources", []),
                "fact_bludgeons": web_research.get("fact_bludgeons", []),
            },
            "meta": {
                "questions_asked": profile.questions_asked,
                "data_quality": (
                    "High" if profile.exposure_confidence > 70 else
                    "Medium" if profile.exposure_confidence > 50 else
                    "Low"
                ),
                "session_tokens": api_client.token_usage.get("session_total", 0),
            },
        }
        
        # Add ranking for multi-option decisions
        if verdict_data.get("ranking"):
            verdict["ranking"] = verdict_data["ranking"]
            verdict["verdict"] = verdict_data.get("verdict", profile.options[0] if profile.options else "")
        
        print(f"\n[VERDICT] >>> FINAL DECISION TAKEN >>>\n"
              f" Status:     {status}\n"
              f" Confidence: {verdict['confidence']}%\n"
              f" Summary:    {verdict['summary'][:100]}...\n"
              f" Logic:      {verdict['the_truth'][:100]}...\n"
              f"----------------------------------------\n", flush=True)

        return verdict
    
    def _fallback_verdict(
        self,
        profile: PsychologyProfile,
        web_research: Dict,
        history: List[Dict]
    ) -> Dict:
        """
        Generate fallback verdict when LLM fails.
        Uses available data (web research, profile) to populate response.
        """
        
        # Determine status based on research sentiment if available
        status = "NO-GO"
        summary = "Unable to generate complete analysis. Defaulting to caution."
        
        sentiment = web_research.get("sentiment_summary", "").lower()
        if "positive" in sentiment or "support" in sentiment:
            status = "caution" # Don't say GO without LLM confirmation
            summary = "Research looks positive, but AI analysis failed. Proceed with caution."
            
        return {
            "status": status,
            "confidence": profile.exposure_confidence,
            "summary": summary,
            "the_truth": "We found data but could not synthesize a final verdict. Review the research below carefully.",
            "rationales": [
                f"Psychology detected: {profile.root_insecurity or 'Unclear motivation'}",
                f"Core fear: {profile.core_fear or 'Unknown'}",
                "Web research was conducted (see below)"
            ],
            "risks": ["Analysis incomplete due to AI service disruption"],
            "deal_breakers": [],
            "success_probability": "Unknown",
            "key_advice": ["Review the community threads below manually", "Trust your gut but verify data"],
            "required_actions": ["Check linked sources"],
            "receipt": [
                {
                    "claimed": profile.weaponizable_phrases[0] if profile.weaponizable_phrases else (profile.stated_reason or "No clean quote captured"),
                    "reality": "Synthesis failed. Only partial evidence remains.",
                }
            ],
            "psychology_exposure": {
                "val": "Partial Data",
                "stated_want": profile.stated_reason,
                "real_want": profile.real_motivation,
                "hidden_fear": profile.hidden_fear,
            },
            "community_sentiment": web_research.get("sentiment_summary", "Unknown"),
            "web_research": web_research,
            "meta": {
                "questions_asked": profile.questions_asked,
                "data_quality": "Partial",
                "session_tokens": api_client.token_usage.get("session_total", 0),
            },
        }
    
    def _empty_web_research(self) -> Dict:
        """Return empty web research structure"""
        return {
            "common_experiences": [],
            "typical_outcomes": {"positive": [], "negative": []},
            "community_advice": [],
            "warning_signs": [],
            "success_patterns": [],
            "failure_patterns": [],
            "sentiment_summary": "No web research conducted",
            "sources": [],
        }


    async def generate_lightweight(
        self,
        query: str,
        research: Dict,
        topic: str = "general"
    ) -> Dict:
        """
        Generate a quick verdicts for low-stakes/lightweight decisions.
        Skips psychological profiling. Focuses on research data.
        """
        if topic == "greeting" or query.lower() in ["hi", "hello"]:
             return {
                "status": "NO-GO",
                "confidence": 100,
                "summary": "Interaction Rejected",
                "the_truth": "I don't do greetings.",
                "psychology_exposure": {"val": "Ignored"},
                "meta": {"is_rejection": True}
             }

        print(f"[VERDICT] Generating LIGHTWEIGHT verdict for: {query}")
        
        # Build prompt
        research_summary = self._summarize_web_research(research)
        
        prompt = f"""You are Ayanokouji Kiyotaka. giving a quick take on a low-stakes decision.
        
This is a lightweight decision (entertainment, food, minor purchase).
No psychological dismantling needed. Be direct. Be useful. Still be yourself — dry, blunt, no fluff.

Decision: "{query}"
Topic: {topic}

Web Research Summary:
{research_summary}

Give a straight answer in 3-4 sentences:
- The key fact they need
- What most people's experience is
- GO or NO-GO with one condition

Sound like you barely care enough to answer — because for this decision, that's the appropriate energy.

Return ONLY JSON:
{{
    "status": "GO|NO-GO",
    "confidence": 85,
    "summary": "2-3 sentence direct answer",
    "condition": "the one thing that matters (e.g. 'Only if you have 200 hours spare')",
     "the_truth": "The core reality of this choice based on research",
    "key_advice": ["Simple advice 1", "Simple advice 2"]
}}
"""
        messages = [{"role": "user", "content": prompt}]
        
        try:
            response = api_client.call_for_verdict(messages, temperature=0.3)
            data = _extract_json_object(response)
            
            if not data:
                raise ValueError("Failed to parse lightweight verdict JSON")
                
            return {
                "status": data.get("status", "GO"),
                "confidence": data.get("confidence", 80),
                "summary": data.get("summary", "Analysis complete."),
                "the_truth": data.get("the_truth", ""),
                "rationales": ["Lightweight decision - based on community consensus"],
                "risks": [], # Low stakes = no risks usually
                "deal_breakers": [],
                "success_probability": "High" if data.get("status") == "GO" else "Low",
                "key_advice": data.get("key_advice", []),
                "required_actions": [data.get("condition", "Proceed if you want.")],
                "psychology_exposure": {
                    "val": "Lightweight",
                    "stated_want": query,
                    "real_want": "Simple Preference",
                    "hidden_fear": "None",
                    "core_delusion": "None"
                },
                "community_sentiment": research.get("sentiment_summary", "Neutral"),
                "web_research": research,
                "meta": {
                    "questions_asked": 0,
                    "data_quality": "Web-Only",
                    "session_tokens": api_client.token_usage.get("session_total", 0),
                    "is_lightweight": True
                },
            }
            
        except Exception as e:
            print(f"[VERDICT] Lightweight generation failed: {e}")
            # Super simple fallback
            return {
                "status": "GO", 
                "confidence": 50,
                "summary": "Research found, but I couldn't summarize it. Check the links.",
                "the_truth": "It's a low-stakes choice. Just flip a coin if you're stuck.",
                "psychology_exposure": {},
                "web_research": research,
                "meta": {"is_lightweight": True}
            }


# Global verdict service instance
verdict_service = VerdictService()
