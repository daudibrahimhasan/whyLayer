import os
import json
import httpx
import time
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv
from enum import Enum
from prompts.ayanokouji_base import PersonaConfig

# Load environment variables
load_dotenv()

# Import Google GenAI SDK
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    print("[WARNING] google-genai not installed. Run: pip install google-genai")

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

class ModelProvider(Enum):
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"

# API Configuration
GEMINI_API_KEY_PRIMARY = (
    os.getenv("GEMINI_API_KEY_PRIMARY")
    or os.getenv("GEMINI_API_KEY")
)
GEMINI_API_KEY_SECONDARY = os.getenv("GEMINI_API_KEY_SECONDARY")
GEMINI_API_KEYS = [key for key in [GEMINI_API_KEY_PRIMARY, GEMINI_API_KEY_SECONDARY] if key]
GROQ_API_KEY_PRIMARY = (
    os.getenv("GROQ_API_KEY_PRIMARY")
    or os.getenv("GROK_API_KEY_PRIMARY")
    or os.getenv("GROQ_API_KEY")
    or os.getenv("GROK_API_KEY")
)
GROQ_API_KEY_SECONDARY = (
    os.getenv("GROQ_API_KEY_SECONDARY")
    or os.getenv("GROK_API_KEY_SECONDARY")
)
GROQ_API_KEYS = [key for key in [GROQ_API_KEY_PRIMARY, GROQ_API_KEY_SECONDARY] if key]
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY")

# API Endpoints
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1/chat/completions"
SAMBANOVA_BASE_URL = "https://api.sambanova.ai/v1/chat/completions"

# Model Configuration
GEMINI_MODEL = "gemini-2.0-flash"  # High quota: 1500 RPM free
GROQ_MODEL = "llama-3.3-70b-versatile"
OPENROUTER_DEFAULT_MODEL = "meta-llama/llama-3.2-3b-instruct:free" 
OPENROUTER_FALLBACK_MODEL = "mistralai/mistral-7b-instruct:free"
CEREBRAS_MODEL = "llama-3.3-70b"
SAMBANOVA_MODEL = "Meta-Llama-3.3-70B-Instruct"

# Flow Control
MIN_QUESTIONS = 3
MAX_QUESTIONS = 12
CONFIDENCE_THRESHOLD_EARLY_EXIT = 85
CONFIDENCE_THRESHOLD_EXTEND = 60
MAX_RETRIES = 2
TIMEOUT_SECONDS = 90.0


# ============================================================================
# CORE API CLIENT
# ============================================================================

class APIClient:
    """Unified API client for Gemini, Groq, and OpenRouter"""
    
    def __init__(self):
        self.token_usage = {"session_total": 0, "last_call": 0}
        self.circuit_breaker = {
            "gemini_fails": 0, 
            "groq_fails": 0, 
            "openrouter_fails": 0,
            "cerebras_fails": 0,
            "sambanova_fails": 0
        }
        self._gemini_last_key_index = None
        self._groq_last_key_index = None

    def _get_gemini_keys(self) -> List[str]:
        """Return Gemini keys in primary -> secondary order."""
        return [key for key in GEMINI_API_KEYS if key]

    def _get_groq_keys(self) -> List[str]:
        """Return Groq keys in primary -> secondary order."""
        return [key for key in GROQ_API_KEYS if key]
    
    # Module-level cached Gemini clients per key to avoid thread-safety issues
    _gemini_clients: Dict[str, "genai.Client"] = {}

    def _get_gemini_client(self, api_key: str) -> "genai.Client":
        """Return a cached GenAI client instance for the given key.
        This avoids setting os.environ (a thread-safety hazard) and
        avoids re-instantiating the client on every call.
        """
        if api_key not in self._gemini_clients:
            self._gemini_clients[api_key] = genai.Client(api_key=api_key)
        return self._gemini_clients[api_key]

    def _call_gemini(self, messages: List[Dict], temperature: float = 0.3, max_tokens: int = 1000) -> Tuple[str, bool]:
        """Call Google Gemini API directly using primary -> secondary key rotation.
        Thread-safe: uses a cached client per key instead of polluting os.environ.
        """
        import logging
        logger = logging.getLogger(__name__)

        gemini_keys = self._get_gemini_keys()
        if not gemini_keys or not GENAI_AVAILABLE:
            logger.warning("Gemini API key or SDK not available")
            return "", False

        system_text = ""
        prompt_parts = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_text = content + "\n\n"
            else:
                prompt_parts.append(content)

        full_prompt = system_text + "\n".join(prompt_parts)

        last_error = None
        for index, api_key in enumerate(gemini_keys):
            try:
                # Thread-safe: use cached client, do NOT set os.environ
                client = self._get_gemini_client(api_key)

                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=full_prompt,
                    config={
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    }
                )

                text = getattr(response, "text", "") or ""
                if not text.strip():
                    raise ValueError("Gemini returned empty text")

                tokens = len(full_prompt.split()) + len(text.split())
                self.token_usage["last_call"] = tokens
                self.token_usage["session_total"] += tokens
                print("\n" + "=" * 60)
                print(f"[LLM] GEMINI ({GEMINI_MODEL})")
                print(f"[TOKENS] ~{tokens} | Session Total: {self.token_usage['session_total']}")
                print("=" * 60 + "\n")

                self._gemini_last_key_index = index
                self.circuit_breaker["gemini_fails"] = 0
                label = "primary" if index == 0 else "secondary"
                logger.info(f"Gemini {label} key success | tokens={tokens}")
                return text, True

            except Exception as e:
                last_error = e
                self.circuit_breaker["gemini_fails"] += 1
                label = "primary" if index == 0 else "secondary"
                logger.error(f"Gemini API Error with {label} key: {e}")
                if "429" in str(e):
                    logger.warning(f"Gemini {label} key hit 429. Trying next key...")
                elif index + 1 < len(gemini_keys):
                    logger.warning(f"Gemini {label} key failed, trying next key...")

        if last_error and "429" in str(last_error):
            logger.warning("All Gemini keys exhausted. Cooling down 2s...")
            time.sleep(2)
        return "", False

    def _call_groq(self, messages: List[Dict], temperature: float = 0.3, max_tokens: int = 1000) -> Tuple[str, bool]:
        """Call Groq API using primary -> secondary key rotation."""
        groq_keys = self._get_groq_keys()
        if not groq_keys:
            print("[WARNING] Groq API key not found")
            return "", False

        payload = {
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        last_error = None
        for index, api_key in enumerate(groq_keys):
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            try:
                with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                    response = client.post(GROQ_BASE_URL, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()

                    if "usage" in data:
                        tokens = data["usage"].get("total_tokens", 0)
                        self.token_usage["last_call"] = tokens
                        self.token_usage["session_total"] += tokens
                        print("\n" + "=" * 60)
                        print("[LLM] GROQ (Llama-3.3-70B)")
                        print(f"[TOKENS] {tokens} | Session Total: {self.token_usage['session_total']}")
                        print("=" * 60 + "\n")

                    self._groq_last_key_index = index
                    self.circuit_breaker["groq_fails"] = 0
                    label = "primary" if index == 0 else "secondary"
                    print(f"[GROQ] {label} key success")
                    return data["choices"][0]["message"]["content"], True

            except Exception as e:
                last_error = e
                self.circuit_breaker["groq_fails"] += 1
                label = "primary" if index == 0 else "secondary"
                print(f"[ERROR] Groq API Error with {label} key: {e}")
                if hasattr(e, "response") and e.response is not None and e.response.status_code == 429:
                    print(f"[RATELIMIT] Groq {label} key hit 429. Trying next key...")
                elif index + 1 < len(groq_keys):
                    print(f"[WARNING] Groq {label} key failed, trying next key...")

        if (
            last_error
            and hasattr(last_error, "response")
            and last_error.response is not None
            and last_error.response.status_code == 429
        ):
            print("[RATELIMIT] All Groq keys exhausted. Cooling down 2s...")
            time.sleep(2)
        return "", False

    def _call_openrouter(self, messages: List[Dict], model: str = OPENROUTER_DEFAULT_MODEL, temperature: float = 0.3, max_tokens: int = 1000) -> Tuple[str, bool]:
        """Call OpenRouter API"""
        if not OPENROUTER_API_KEY:
            print("[WARNING] OpenRouter API key not found")
            return "", False
            
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://whyLayer",
            "X-Title": "whyLayer Decision Intelligence"
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        try:
            with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                response = client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # Track tokens
                if "usage" in data:
                    tokens = data["usage"].get("total_tokens", 0)
                    self.token_usage["last_call"] = tokens
                    self.token_usage["session_total"] += tokens
                    print("\n" + "="*60)
                    print(f"🤖 LLM: OPENROUTER ({model.split('/')[-1]})")
                    print(f"📊 Tokens: {tokens} | Session Total: {self.token_usage['session_total']}")
                    print("="*60 + "\n")
                
                self.circuit_breaker["openrouter_fails"] = 0  # Reset on success
                return data["choices"][0]["message"]["content"], True
                
        except Exception as e:
            self.circuit_breaker["openrouter_fails"] += 1
            print(f"[ERROR] OpenRouter API Error: {e}")
            if hasattr(e, 'response') and e.response.status_code == 429:
                print("[RATELIMIT] OpenRouter 429 detected. Cooling down 2s...")
                time.sleep(2)
            return "", False

    def _call_cerebras(self, messages: List[Dict], temperature: float = 0.3, max_tokens: int = 1000) -> Tuple[str, bool]:
        """Call Cerebras API (Ultra-fast, Llama 3.1 70B)"""
        if not CEREBRAS_API_KEY:
            # Silent fallback if not key
            return "", False
            
        headers = {
            "Authorization": f"Bearer {CEREBRAS_API_KEY}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": CEREBRAS_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens  # Fast inference
        }
        
        try:
            with httpx.Client(timeout=30.0) as client:  # Faster timeout for Cerebras
                response = client.post(CEREBRAS_BASE_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # Track tokens
                if "usage" in data:
                    tokens = data["usage"].get("total_tokens", 0)
                    self.token_usage["last_call"] = tokens
                    self.token_usage["session_total"] += tokens
                    print("\n" + "="*60)
                    print(f"⚡ LLM: CEREBRAS (Llama 3.1 70B)")
                    print(f"📊 Tokens: {tokens} | Session Total: {self.token_usage['session_total']}")
                    print("="*60 + "\n")
                
                self.circuit_breaker["cerebras_fails"] = 0
                return data["choices"][0]["message"]["content"], True
                
        except Exception as e:
            self.circuit_breaker["cerebras_fails"] += 1
            print(f"[ERROR] Cerebras API Error: {e}")
            return "", False

    def _call_sambanova(self, messages: List[Dict], temperature: float = 0.2) -> Tuple[str, bool]:
        """Call SambaNova API (Llama 3.1 405B - Deep Reasoning)"""
        if not SAMBANOVA_API_KEY:
            return "", False
            
        headers = {
            "Authorization": f"Bearer {SAMBANOVA_API_KEY}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": SAMBANOVA_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2000  # Allow detailed verdicts
        }
        
        try:
            with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                response = client.post(SAMBANOVA_BASE_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                
                # Track tokens
                if "usage" in data:
                    tokens = data["usage"].get("total_tokens", 0)
                    self.token_usage["last_call"] = tokens
                    self.token_usage["session_total"] += tokens
                    print("\n" + "="*60)
                    print(f"🧠 LLM: SAMBANOVA (Llama 3.1 405B)")
                    print(f"📊 Tokens: {tokens} | Session Total: {self.token_usage['session_total']}")
                    print("="*60 + "\n")
                
                self.circuit_breaker["sambanova_fails"] = 0
                return data["choices"][0]["message"]["content"], True
                
        except Exception as e:
            self.circuit_breaker["sambanova_fails"] += 1
            print(f"[ERROR] SambaNova API Error: {e}")
            return "", False
    
    def call_with_fallback(
        self,
        messages: List[Dict],
        prefer_gemini: bool = True,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        prefer_groq: bool = None,
    ) -> str:
        """
        Call API with intelligent fallback chain.
        Supports legacy prefer_groq for compatibility.
        """
        # Legacy compatibility: if prefer_groq is set, use it to set prefer_gemini
        if prefer_groq is not None:
            prefer_gemini = not prefer_groq

        gemini_available = self.circuit_breaker["gemini_fails"] < 3 and bool(self._get_gemini_keys()) and GENAI_AVAILABLE
        groq_available = self.circuit_breaker["groq_fails"] < 3 and bool(self._get_groq_keys())
        openrouter_available = self.circuit_breaker["openrouter_fails"] < 3 and OPENROUTER_API_KEY

        
        try:
            # Try Gemini first if preferred
            if prefer_gemini and gemini_available:
                response, success = self._call_gemini(messages, temperature, max_tokens)
                if success:
                    return response
                print("[WARNING] Gemini failed, trying Groq...")
            
            # Try Groq (fast)
            if groq_available:
                response, success = self._call_groq(messages, temperature, max_tokens)
                if success:
                    return response
                print("[WARNING] Groq failed, trying OpenRouter...")
            
            # Try OpenRouter with default model
            if openrouter_available:
                response, success = self._call_openrouter(messages, OPENROUTER_DEFAULT_MODEL, temperature, max_tokens)
                if success:
                    return response
                print("[WARNING] OpenRouter default failed, trying fallback model...")
                
                # Try fallback model
                response, success = self._call_openrouter(
                    messages, OPENROUTER_FALLBACK_MODEL, temperature=temperature, max_tokens=max_tokens
                )
                if success:
                    return response
            
            # Last resort: try Gemini again if we haven't
            if not prefer_gemini and gemini_available:
                response, success = self._call_gemini(messages, temperature, max_tokens)
                if success:
                    return response
        except Exception:
            return "Let’s simplify this: what’s bothering you the most about this situation?"
            
        return "Let’s simplify this: what’s bothering you the most about this situation?"
    
    def call_for_interrogation(
        self,
        messages: List[Dict],
        temperature: float = 0.3,
        max_tokens: int = 300,
    ) -> str:
        return self.call_with_fallback(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            prefer_groq=True,
        )
    
    def call_for_verdict(
        self, messages: List[Dict], temperature: float = 0.2, max_tokens: int = 1000
    ) -> str:
        """
        Call for final verdict analysis (Phase 5).
        Priority: SambaNova (405B Deep Reasoning) > Gemini > OpenRouter > Groq.
        """
        print("[VERDICT-LLM] Starting verdict generation...")
        
        sambanova_available = self.circuit_breaker["sambanova_fails"] < 3 and bool(SAMBANOVA_API_KEY)
        gemini_available = self.circuit_breaker["gemini_fails"] < 3 and bool(self._get_gemini_keys()) and GENAI_AVAILABLE
        openrouter_available = self.circuit_breaker["openrouter_fails"] < 3 and bool(OPENROUTER_API_KEY)
        groq_available = self.circuit_breaker["groq_fails"] < 3 and bool(self._get_groq_keys())
        
        print(f"[VERDICT-LLM] Available: SambaNova={sambanova_available}, Gemini={gemini_available}, OpenRouter={openrouter_available}")
        
        # 1. SambaNova (Best for complex reasoning)
        if sambanova_available:
            print("[VERDICT-LLM] Trying SambaNova (405B)...")
            response, success = self._call_sambanova(messages, temperature)
            if success and response and len(response.strip()) > 10:
                print(f"[VERDICT-LLM] SambaNova success! Response length: {len(response)}")
                return response
            print("[WARNING] SambaNova failed, trying Gemini...")

        # 2. Gemini
        if gemini_available:
            print("[VERDICT-LLM] Trying Gemini...")
            response, success = self._call_gemini(messages, temperature, max_tokens)
            if success and response and len(response.strip()) > 10:
                print(f"[VERDICT-LLM] Gemini success! Response length: {len(response)}")
                return response
            elif success:
                print(f"[VERDICT-LLM] Gemini returned empty/short response: '{response[:50]}'")
            print("[WARNING] Gemini failed for verdict, trying OpenRouter...")
        
        # 3. OpenRouter fallback
        if openrouter_available:
            print("[VERDICT-LLM] Trying OpenRouter...")
            response, success = self._call_openrouter(messages, OPENROUTER_DEFAULT_MODEL, temperature, max_tokens)
            if success and response and len(response.strip()) > 10:
                print(f"[VERDICT-LLM] OpenRouter success! Response length: {len(response)}")
                return response
            print("[WARNING] OpenRouter failed, trying Groq...")
        
        # 4. Groq as last resort
        if groq_available:
            print("[VERDICT-LLM] Trying Groq...")
            response, success = self._call_groq(messages, temperature, max_tokens)
            if success and response and len(response.strip()) > 10:
                print(f"[VERDICT-LLM] Groq success! Response length: {len(response)}")
                return response
        
        print("[VERDICT-LLM] All providers failed!")
        raise Exception("All API providers failed for verdict.")


# Global client instance
api_client = APIClient()

# ============================================================================
# CONTEXT MANAGEMENT
# ============================================================================

class ContextManager:
    """Manages conversation history with smart compression"""
    
    @staticmethod
    def compress_history(history: List[Dict], max_pairs: int = 3) -> str:
        """
        Compress history to stay within token limits
        - Keep original query always
        - Keep last N Q&A pairs verbatim
        - Summarize older pairs into insights
        """
        if len(history) <= max_pairs:
            return "\n".join([f"Q: {h['question']}\nA: {h['answer']}" for h in history])
        
        # Keep recent pairs
        recent = history[-max_pairs:]
        recent_context = "\n".join([f"Q: {h['question']}\nA: {h['answer']}" for h in recent])
        
        # Summarize older pairs
        older = history[:-max_pairs]
        insights = []
        for h in older:
            q = h['question'].lower()
            a = h['answer'].lower()
            
            # Extract key insights
            if 'hesitat' in q or 'why now' in q:
                insights.append(f"- Hesitation detected: {h['answer'][:50]}...")
            elif 'fear' in q or 'risk' in q:
                insights.append(f"- Fear/Risk identified: {h['answer'][:50]}...")
            elif 'backup' in q or 'plan b' in q:
                insights.append(f"- Contingency: {h['answer'][:50]}...")
        
        compressed = "PREVIOUS INSIGHTS:\n" + "\n".join(insights) + "\n\nRECENT EXCHANGES:\n" + recent_context
        return compressed

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _extract_json_object(text: str) -> Optional[Dict]:
    """Extract JSON object from LLM response"""
    if not text:
        print("[ERROR] JSON extraction: empty input")
        return None
        
    try:
        # Step 1: Remove markdown code blocks aggressively
        import re
        text = re.sub(r'```json\s*\n?', '', text)
        text = re.sub(r'```\s*\n?', '', text)
        text = re.sub(r'```JSON\s*\n?', '', text, flags=re.IGNORECASE)
        
        # Step 2: Normalize whitespace
        text = text.strip()
        
        # Step 3: Fix double-brace escaping from f-string/format() contamination
        # Only fix if the text has {{ but not {{{ (triple-brace is different)
        if '{{' in text and '{{{' not in text:
            text = text.replace('{{', '{').replace('}}', '}')
        
        # Step 4: Find JSON object boundaries
        start = text.find('{')
        end = text.rfind('}') + 1
        
        if start != -1 and end > start:
            json_str = text[start:end]
            result = json.loads(json_str)
            print(f"[DEBUG] JSON extraction successful: {list(result.keys())[:3]}...")
            return result
        else:
            print(f"[ERROR] JSON extraction: no braces found in text: '{text[:100]}...'")
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON decode failed: {e}")
        print(f"[ERROR] Attempted to parse: '{text[start:end][:200]}...'")
    except Exception as e:
        print(f"[ERROR] JSON extraction failed: {e}")
    
    return None


def _extract_json_list(text: str) -> Optional[List[Dict]]:
    """Extract JSON list from LLM response"""
    try:
        # Remove markdown code blocks
        text = text.replace('```json', '').replace('```', '')
        
        # Find JSON array boundaries
        start = text.find('[')
        end = text.rfind(']') + 1
        
        if start != -1 and end > start:
            json_str = text[start:end]
            return json.loads(json_str)
    except Exception as e:
        print(f"[ERROR] JSON extraction failed: {e}")
    
    return None


def get_session_stats() -> Dict:
    """Get current session statistics"""
    return {
        "total_tokens_used": api_client.token_usage['session_total'],
        "last_call_tokens": api_client.token_usage['last_call'],
        "groq_circuit_failures": api_client.circuit_breaker['groq_fails'],
        "openrouter_circuit_failures": api_client.circuit_breaker['openrouter_fails'],
        "cerebras_circuit_failures": api_client.circuit_breaker['cerebras_fails'],
        "sambanova_circuit_failures": api_client.circuit_breaker['sambanova_fails']
    }


def reset_session():
    """Reset session state (useful for new conversation)"""
    api_client.token_usage = {"session_total": 0, "last_call": 0}
    api_client.circuit_breaker = {
        "gemini_fails": 0, "groq_fails": 0, "openrouter_fails": 0,
        "cerebras_fails": 0, "sambanova_fails": 0
    }
    print("[SUCCESS] Session reset")


# ============================================================================
# SAFE LLM WRAPPER (MOST IMPORTANT) P1
# ============================================================================

def safe_parse_json(text: str):
    """Extract JSON safely from messy LLM output."""
    if not text:
        return None

    # Try direct parse
    try:
        return json.loads(text)
    except:
        pass

    repaired = text.strip()
    repaired = re.sub(r"```(?:json|JSON)?\s*", "", repaired)
    repaired = re.sub(r"\s*```", "", repaired)
    repaired = repaired.replace("“", '"').replace("”", '"').replace("’", "'")

    try:
        return json.loads(repaired)
    except:
        pass

    # Try to extract JSON block
    match = re.search(r"\{.*\}", repaired, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except:
            return None

    return None

def normalize_llm_output(parsed: dict):
    """Force consistent structure."""
    if not parsed or not isinstance(parsed, dict):
        return None

    return {
        "text": parsed.get("text") or parsed.get("spoken_statement") or "",
        "type": parsed.get("type", "question"),
        "vector": parsed.get("vector") or parsed.get("purpose") or "unknown",
        "raw": parsed
    }

def safe_llm_call(call_fn, *args, **kwargs):
    """Bulletproof LLM call wrapper."""
    try:
        response = call_fn(*args, **kwargs)

        if not response or not isinstance(response, str):
            raise ValueError("Empty or invalid LLM response")

        parsed = safe_parse_json(response)
        normalized = normalize_llm_output(parsed)

        if not normalized or not normalized["text"]:
            # If the parser couldn't normalize a single question but it gave us raw JSON 
            # (e.g. initial questions payload which just has "questions" list),
            # we should still return the raw parsed object so the caller can handle it
            if parsed and isinstance(parsed, dict):
                return {
                    "text": "batch_generation", 
                    "type": "batch", 
                    "vector": "unknown",
                    "raw": parsed
                }
            raise ValueError("Invalid parsed structure")

        return normalized

    except Exception as e:
        print("[SAFE LLM FALLBACK]", str(e))

        return {
            "text": "You're answering around it.",
            "type": "observation",
            "vector": "fallback",
            "raw": {}
        }
