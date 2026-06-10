<div align="center">
<img width="1200" height="475" alt="whyLayer Banner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />

# whyLayer

**Decision Intelligence Engine** — Precision psychology disguised as decision help.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React_19-61DAFB?style=flat-square&logo=react)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/Language-TypeScript-3178C6?style=flat-square&logo=typescript)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Language-Python_3.13-3776AB?style=flat-square&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat-square)](LICENSE)

</div>

---

## What is whyLayer?

whyLayer is a decision intelligence engine that interrogates your decisions before you make them. It uses multi-LLM psychological profiling to expose hidden fears, delusions, and real motivations — then delivers a brutally honest GO / NO-GO verdict backed by web research evidence.

**You describe a decision. It cross-examines you. It tells you the truth.**

### Core Features

- **Psychological Interrogation** — Dynamic multi-phase questioning that adapts to your responses
- **Multi-LLM Cascade** — Groq → SambaNova → Gemini → OpenRouter fallback chain
- **Evidence Hunting** — Automated web research to validate or destroy your assumptions
- **GO / NO-GO Verdicts** — Clear, final, research-backed decisions with confidence scores
- **Lightweight Routing** — Trivial decisions (food, entertainment) get instant answers without interrogation
- **Google OAuth** — Sign in with Google for extended usage limits
- **Offline-First Telemetry** — Privacy-respecting, local-only event tracking (zero external calls)

---

## Tech Stack

| Layer      | Technology                                     |
| ---------- | ---------------------------------------------- |
| Frontend   | React 19, TypeScript, Vite                     |
| Backend    | Python 3.13, FastAPI, Uvicorn                  |
| Database   | SQLite (via SQLAlchemy)                        |
| Auth       | JWT sessions + Google OAuth                    |
| LLM APIs   | Groq, Gemini, SambaNova, Cerebras, OpenRouter  |
| Search     | Serper, Jina, DuckDuckGo (fallback)            |
| Testing    | Vitest (frontend), Pytest (backend)            |

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **npm**

### 1. Clone

```bash
git clone https://github.com/your-username/whyLayer.git
cd whyLayer
```

### 2. Backend Setup

```bash
cd backend
pip install -r requirements.txt
```

Create a `.env` file (see `.env.example` for the template) and fill in your API keys:

```env
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
SAMBANOVA_API_KEY=your_key_here
GOOGLE_CLIENT_ID=your_id_here
GOOGLE_CLIENT_SECRET=your_secret_here
JWT_SECRET_KEY=generate_with_openssl_rand_hex_32
```

Start the backend:

```bash
python main.py
```

Backend runs at `http://127.0.0.1:8000`

### 3. Frontend Setup

Open a **new terminal**:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`

### 4. Open in Browser

Go to **http://localhost:3000** — you're ready.

---

## Project Structure

```
whyLayer/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── .env                     # API keys (local-only, never committed)
│   ├── middleware/
│   │   ├── security.py          # CSRF, CORS, Security Headers
│   │   └── rate_limit.py        # Rate limiting
│   ├── prompts/
│   │   ├── ayanokouji_base.py   # Persona & attack philosophy
│   │   └── interrogation.py     # Question generation prompts
│   ├── services/
│   │   ├── llm_service.py       # Multi-LLM cascade
│   │   ├── interrogation_service.py
│   │   ├── answer_analyzer.py
│   │   ├── evidence_hunter.py
│   │   ├── search_service.py
│   │   └── verdict_service.py
│   ├── utils/
│   │   ├── jwt.py               # JWT token management
│   │   └── fingerprint.py       # Identity fingerprinting
│   ├── database/
│   │   ├── models.py
│   │   └── connection.py
│   ├── routers/
│   │   ├── chat.py              # /api/decision/*
│   │   ├── auth.py              # /api/auth/*
│   │   └── history.py           # /api/history/*
│   └── tests/
│       ├── test_main.py
│       └── test_jwt.py
│
├── frontend/
│   ├── index.tsx                # Main React app
│   ├── index.css                # Global styles
│   ├── types.ts                 # TypeScript types
│   ├── telemetry.ts             # Local-only event tracking
│   ├── vite.config.ts           # Vite + Vitest config
│   ├── components/
│   │   ├── ErrorBoundary.tsx
│   │   ├── ComputationOverlay.tsx
│   │   ├── DottedGlowBackground.tsx
│   │   ├── StatusStates.tsx
│   │   └── Icons.tsx
│   └── public/
│
├── ARCHITECTURE.md              # Full system design docs
├── .gitignore
└── README.md
```

---

## Available Scripts

### Frontend

| Command           | Description                    |
| ----------------- | ------------------------------ |
| `npm run dev`     | Start dev server (port 3000)   |
| `npm run build`   | Type-check + production build  |
| `npm run test`    | Run unit tests (Vitest)        |
| `npm run lint`    | Run ESLint                     |
| `npm run format`  | Format code with Prettier      |

### Backend

| Command                      | Description                    |
| ---------------------------- | ------------------------------ |
| `python main.py`             | Start dev server (port 8000)   |
| `python -m pytest tests/`   | Run backend tests              |

---

## Environment Variables

| Variable               | Required | Purpose                       |
| ---------------------- | -------- | ----------------------------- |
| `GROQ_API_KEY`         | Yes      | Fast interrogation LLM        |
| `GEMINI_API_KEY`       | Yes      | Verdicts & fallbacks          |
| `SAMBANOVA_API_KEY`    | Yes      | Deep reasoning verdicts       |
| `CEREBRAS_API_KEY`     | Optional | Ultra-fast fallback           |
| `OPENROUTER_API_KEY`   | Optional | General fallback              |
| `SERPER_API_KEY`       | Optional | Web search (primary)          |
| `JINA_API_KEY`         | Optional | Web search (secondary)        |
| `GOOGLE_CLIENT_ID`     | Yes      | Google OAuth login             |
| `GOOGLE_CLIENT_SECRET` | Yes      | Google OAuth login             |
| `JWT_SECRET_KEY`       | Yes      | Session token signing          |

> **Note:** All keys run through free tiers. This is free because every API used offers a generous free tier (Groq: 14k req/day, Gemini: 1500/day, etc).

---

## How It Works

```
User types a decision
        │
        ▼
   ┌─────────────┐
   │  Classifier  │──── Greeting? → Reject
   └─────┬───────┘──── Lightweight? → Instant verdict
         │
         ▼ (Serious decision)
   ┌─────────────┐
   │ Interrogation│ ← 3-9 dynamic questions
   │   Service    │ ← Adapts attack vectors per answer
   └─────┬───────┘
         │
         ▼
   ┌─────────────┐
   │  Evidence    │ ← Web research + fact checking
   │   Hunter     │
   └─────┬───────┘
         │
         ▼
   ┌─────────────┐
   │   Verdict    │ → GO / NO-GO + confidence %
   │   Service    │ → Psychology exposure
   └─────────────┘ → Key advice
```

---

## Security

- **JWT Sessions** — Signed tokens replace fingerprint-only identity
- **CSRF Protection** — Origin/referer validation on mutating requests
- **Security Headers** — CSP, HSTS, X-Frame-Options on every response
- **Rate Limiting** — 1 decision/session (guest), 2/day (logged in)
- **No Client-Side Secrets** — All LLM calls proxied through backend
- **Local-Only Data** — Telemetry stays in localStorage, never leaves device

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
