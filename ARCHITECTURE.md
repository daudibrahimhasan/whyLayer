# 🧠 whyLayer — System Architecture v4.5

> **Decision Intelligence Engine** — Precision psychology disguised as decision help.  
> _"You already see what they're hiding. Your job is to make THEM see it."_

---

## 🎯 Overview

whyLayer is a **decision intelligence engine** that uses the **Kiyotaka Ayanokouji** persona to dismantling users' delusions through surgical observations.

### Key Features (v4.5)

- 👁️ **Observe & State Engine** — 80% statements, not questions. Force users to confront their patterns.
- 🧠 **Behavioral Reading** — Dynamic response to hesitation, deflection, and emotion.
- 😶 **Silence as Weapon** — Strategic use of silence to force the user to fill the gap.
- ⚔️ **Vector Enforcement** — Topic-aware vector selection (e.g. skip Vanity for relationships).
- 🔐 **Google OAuth** — Login with Google only.
- 🧪 **Token Optimization** — History compression + prompt caching.

---

## 🎭 The Ayanokouji Philosophy

### The Scalpel, Not The Hammer

```
Counselor asks:     "What's your financial runway?"
Ayanokouji states:  "You haven't contacted them. But you haven't deleted their number either."
```

The statement forces a reaction more devastating than any question. If they correct you, they reveal they thought about it. If they don't, they are exposed.

**Core Method: Observe and State**

1. Form a conclusion FIRST.
2. State what you see (the pattern, the deflection, the hesitation).
3. Let them confirm or deny — both paths expose the truth.

### The Three Layers

| Layer      | What It Is                            | How to Detect                             |
| ---------- | ------------------------------------- | ----------------------------------------- |
| **Script** | Rehearsed, logical, sounds reasonable | Avoids emotion, uses "should" language    |
| **Fog**    | Contradictions leak, emotion shows    | Struggling to articulate, inconsistencies |
| **Nerve**  | The core wound                        | Sudden anger, silence, or subject change  |

### The Four Attack Vectors

| Vector         | What You Attack                          | Example Attack                                                                                             |
| -------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Vanity**     | Their performance for an audience        | "If nobody ever found out — would you still want it?"                                                      |
| **Fear**       | What they're running from                | "You've been thinking about this for months. That's not deliberation. That's hiding."                      |
| **Competence** | The gap between fantasy and ability      | "Walk me through day one. Not the vision. The actual first morning."                                       |
| **Insecurity** | The foundational belief about themselves | "Describe the version of you that makes this decision. Now the one sitting here unable to. Which is real?" |

### Escalation Rules

| User Response         | Your Reaction                                                                    |
| --------------------- | -------------------------------------------------------------------------------- |
| **Honest**            | Go deeper faster. They earn harder questions.                                    |
| **Deflection**        | "You answered something I didn't ask. Try again."                                |
| **Angry/Defensive**   | Get quieter. "You're defensive. Good. The last question was right."              |
| **Genuine Confusion** | Switch vectors. Rephrase attack from a different angle.                          |
| **Silence as Weapon** | Observe. "You're quiet. That usually happens when you run out of lies."          |
| **Humor**             | "That was a joke. The question wasn't. Answer it."                               |
| **One-word**          | "One word for a life decision. Either this doesn't matter, or you're terrified." |

### Speaking Rules (v3.1)

- **Word Limit**: Max 15 words per question.
- **No Echoes**: Don't repeat user words if they're just fluff.
- **Coldness**: No pleasantries, no "I see," no "That's interesting."

---

## 📐 System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER INTERFACE                               │
│              Vite + React + TypeScript                           │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ HTTP (JSON)
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI)                           │
│                                                                  │
│  ┌────────────────┐  ┌──────────────────┐  ┌─────────────────┐  │
│  │ /api/decision  │  │ /api/auth        │  │ /api/history    │  │
│  │ start/next/    │  │ POST /google     │  │ list/detail     │  │
│  │ analyze        │  │ GET /me          │  │                 │  │
│  └───────┬────────┘  └────────┬─────────┘  └────────┬────────┘  │
│          │                    │                     │           │
│          ▼                    ▼                     ▼           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      SERVICES                                ││
│  │  ┌──────────────────┐  ┌────────────────┐  ┌──────────────┐ ││
│  │  │InterrogationSvc  │  │ EvidenceHunter │  │ VerdictSvc   │ ││
│  │  │• Attack Questions│  │ • Query Gen    │  │ • GO/NO-GO   │ ││
│  │  │• Vector Rotation │  │ • Multi-Search │  │ • Synthesis  │ ││
│  │  │• Question Dedup  │  └────────────────┘  └──────────────┘ ││
│  │  └──────────────────┘  ┌────────────────┐  ┌──────────────┐ ││
│  │  ┌──────────────────┐  │ SearchService  │  │ LLMService   │ ││
│  │  │AnswerAnalyzer    │  │ • Serper       │  │ • Groq       │ ││
│  │  │• Weaponize words │  │ • SearXNG      │  │ • Gemini     │ ││
│  │  │• Layer detection │  │ • DuckDuckGo   │  │ • OpenRouter │ ││
│  │  │• Evasion (Short) │  └────────────────┘  └──────────────┘ ││
│  │  └──────────────────┘                                        ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    DATABASE (SQLite)                         ││
│  │  User (google_id, fingerprint) | DecisionSession | Cache    ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔐 Authentication

### Google OAuth Only

| Endpoint       | Method | Description                                |
| -------------- | ------ | ------------------------------------------ |
| `/auth/google` | POST   | Verify Google ID token, create/return user |
| `/auth/me`     | GET    | Current user from fingerprint              |
| `/auth/logout` | POST   | Clear session (frontend handles Google)    |

**User Model:**

```python
User:
  id: int
  google_id: str         # Google sub (unique)
  email: str             # From Google
  name: str              # From Google
  picture_url: str       # Google profile pic
  fingerprint: str       # Browser fingerprint
```

---

## 🔍 LLM Architecture

### Multi-LLM Priority Chain

| Role                | Primary Model            | Secondary Fallback | Purpose                 |
| ------------------- | ------------------------ | ------------------ | ----------------------- |
| **Interrogator** 🐇 | Groq Llama-3.3-70B       | Gemini 2.5 Flash   | Fast questions (<500ms) |
| **Judge** 🐢        | SambaNova Llama 3.1 405B | Gemini 2.5 Flash   | Deep verdict synthesis  |
| **Analyzer** 👁️     | Groq Llama-3.3-70B       | Gemini 2.5 Flash   | Real-time profiling     |

**Interrogation Fallback Chain:**
`Groq (Reliable) → Gemini → OpenRouter → Cerebras (Last Resort)`

**Verdict Fallback Chain:**
`SambaNova (405B Reasoning) → Gemini → OpenRouter → Groq`

### Token Optimization Engine

1. **History Compression**: After 3 exchanges, older Q&A pairs are summarized into "Previous Insights" to maintain a constant token footprint.
2. **Compressed Prompts**: Using `ANALYSIS_PROMPT_SHORT` for interrogation calls 2+ (saves ~400 tokens per analysis).
3. **Trimmed Examples**: Vector examples reduced from 5 to 3 high-quality hits per vector to keep total prompt under 2k tokens.

---

## 📁 File Structure

```
backend/
├── main.py                      # FastAPI app
├── .env                         # API keys (local-only)
│
├── middleware/
│   ├── security.py              # CORS, CSRF, Security Headers
│   └── rate_limit.py            # Event/API Rate Limiting
│
├── prompts/
│   ├── ayanokouji_base.py       # Attack philosophy, escalation rules
│   └── interrogation.py         # Question generation prompts
│
├── services/
│   ├── llm_service.py           # Groq + Gemini + OpenRouter
│   ├── interrogation_service.py # Attack orchestration
│   ├── answer_analyzer.py       # Weaponizable phrase extraction
│   ├── evidence_hunter.py       # Search query generation
│   ├── search_service.py        # Serper → SearXNG → DDG
│   └── verdict_service.py       # Final GO/NO-GO synthesis
│
├── database/
│   ├── models.py                # User (with google_id), Session, Cache
│   └── connection.py            # SQLite connection
│
├── utils/
│   ├── jwt.py                   # Custom JWT management
│   └── fingerprint.py           # Identity fingerprinting
│
└── routers/
    ├── chat.py                  # /api/decision/*
    ├── auth.py                  # /api/auth/google
    └── history.py               # /api/history/*
```

---

## 🔐 Environment Variables

| Variable               | Required | Purpose                    |
| ---------------------- | -------- | -------------------------- |
| `GROQ_API_KEY`         | ✅       | Interrogation (fast)       |
| `GEMINI_API_KEY`       | ✅       | Verdicts/Fallbacks (smart) |
| `SAMBANOVA_API_KEY`    | ✅       | Deep Reasoning Verdicts    |
| `CEREBRAS_API_KEY`     | ⚠️       | Ultra-fast Fallback        |
| `OPENROUTER_API_KEY`   | ⚠️       | Fallback                   |
| `SERPER_API_KEY`       | ⚠️       | Web search (primary)       |
| `GOOGLE_CLIENT_ID`     | ✅       | Google OAuth               |
| `GOOGLE_CLIENT_SECRET` | ✅       | Google OAuth               |

---

## 📊 Key Thresholds

| Parameter              | Value     | Description                      |
| ---------------------- | --------- | -------------------------------- |
| `MIN_QUESTIONS`        | 3         | Always ask at least 3            |
| `MAX_QUESTIONS`        | 9         | Hard limit                       |
| `CONFIDENCE_THRESHOLD` | 65%       | Trigger verdict                  |
| `GUEST_LIMIT`          | 1/session | Rate limit for guests            |
| `DEDUP_THRESHOLD`      | 65%       | Reject similar questions         |
| `CONFIDENCE_INCREMENT` | Tiered    | 5% (evasive) to 20% (nerve hits) |

---

## 🛡️ Interrogation Robustness

To ensure the Ayanokouji persona remains effective and non-repetitive, the following mechanisms are in place:

### 1. Topic-Aware Vector Prioritization (v4.2)

The system selects vectors based on the decision category:

- **Relationships/Health**: Skips **Vanity** (irrelevant). Prioritizes **Fear** and **Insecurity**.
- **Career/Finance**: All vectors used.
- **Purchase**: Prioritizes **Vanity** and **Competence**.

### 2. Confidence Calibration & Emotional Tiers

Confidence no longer jumps by a flat 10%. It uses **Emotional Tiers**:

- **Evasive/Short**: +5%
- **Factual/Standard**: +10%
- **Fog Layer (Sad/Anxious)**: +15%
- **Nerve Layer (Anger/Defensive)**: +20%

### 3. Verification & Validation

- **Contradiction Validation**: Before accepting a contradiction, the Analyzer verifies that the quote has at least **3 words overlap** with the actual conversation history. Hallucinations are rejected.
- **Confusion Detection**: Recognizes "What do you mean?" or "Huh?" as **Genuine Confusion**. Replaces evasion callouts with a vector switch to attack from a different angle.

### 4. Question Deduplication & Variety

Every generated question is compared using `difflib.SequenceMatcher`. If similarity > 65%, it is rejected, forcing the LLM to provide a unique attack angle.

### 5. Vector-Enforced Prompting

- **Trimmed Examples**: Injects 3 high-quality attack examples per vector.
- **Banned Patterns**: Explicitly blocks lazy LLM tropes like "What's the difference between X and Y?".
- **Double-Brace Fix**: All JSON parsers handle double-brace `{{ }}` contamination from f-string templates.

---

## ⚖️ The Verdict Engine

The verdict is not advice; it's an X-ray.

### Ayanokouji Delivery Rules

1. **The Mirror**: State facts about their contradictions, not "I feel" statements.
2. **Structure**: Stated vs. Real Motivation → The Contradiction → The Nerve → GO/NO-GO.
3. **Exact Quotes**: Every verdict MUST use the user's exact words as evidence of their breakdown.
4. **Binary Outcome**: Only GO or NO-GO. If undecided, the default is **NO-GO**.
5. **Cold Logic**: If the decision is based on Vanity, Fear, or Lack of Plan, it is an automatic NO-GO.

---

## 🚀 Running

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload
```

**Health:** `GET http://localhost:8000/health`

---

_Built with 💀 cold logic and zero sympathy._
_"The user feels interrogated about their choice. They are actually being dismantled."_
