# main.py
"""
whyLayer Backend - Decision Intelligence Engine
FastAPI app with JWT auth, CSRF protection, tightened CORS.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("request_logger")
from dotenv import load_dotenv

# Load env vars first — before any module that reads them
load_dotenv()

# Import routers
from routers import chat, auth, history

# Import database
from database.connection import init_db

# Import security middleware
from middleware.security import SecurityMiddleware, ALLOWED_ORIGINS


def validate_required_env_vars():
    """Check that all required environment variables are set.
    Logs a WARNING for each missing var but does not crash.
    """
    required_vars = {
        "GROQ_API_KEY": "Primary LLM provider for interrogation",
        "GEMINI_API_KEY": "Secondary LLM provider for classification/fallback",
        "JWT_SECRET_KEY": "JWT signing key for authentication",
        "GOOGLE_CLIENT_ID": "Google OAuth client ID",
        "GOOGLE_CLIENT_SECRET": "Google OAuth client secret",
    }
    all_ok = True
    for var_name, description in required_vars.items():
        if not os.getenv(var_name):
            logger.warning(
                "[ENV] MISSING REQUIRED ENV VAR: %s — %s",
                var_name,
                description,
            )
            all_ok = False
    if all_ok:
        logger.info("[ENV] All required environment variables are set.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    print("[STARTUP] Initializing whyLayer Backend...")
    validate_required_env_vars()
    init_db()
    print("[STARTUP] Database initialized")
    print(f"[STARTUP] CORS allowed origins: {ALLOWED_ORIGINS}")
    print("[STARTUP] Ready to serve requests")
    yield
    print("[SHUTDOWN] whyLayer Backend shutting down...")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="whyLayer Backend",
    description="Decision Intelligence Engine — YLY",
    version="2.2.0",
    lifespan=lifespan,
    # Disable automatic OpenAPI docs in production
    docs_url="/docs" if os.getenv("APP_ENV", "development") == "development" else None,
    redoc_url=None,
)

# ─── Middleware (order matters — outermost runs first) ────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(
        f"Method={request.method} Path={request.url.path} "
        f"Status={response.status_code} Time={process_time:.3f}s"
    )
    return response

# 1. CSRF + security headers (innermost wrapping — runs before CORS)
app.add_middleware(SecurityMiddleware)

# 2. CORS — only allow configured origins, no wildcards
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),   # loaded from ALLOWED_ORIGINS env var
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["X-Request-Id"],
    max_age=600,
)

# ─── Routers ──────────────────────────────────────────────────────────────────

app.include_router(chat.router, prefix="/api/decision", tags=["decision"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(history.router, prefix="/api", tags=["history"])


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """Health check — safe to expose publicly."""
    return {"status": "ok", "version": "2.2.0", "service": "whyLayer"}


@app.get("/")
def root():
    """Root — minimal info only."""
    return {"name": "whyLayer Decision Intelligence Engine", "version": "2.2.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",  # Bind to localhost only — use a reverse proxy for production
        port=8000,
        reload=True,
    )
