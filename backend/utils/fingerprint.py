# utils/fingerprint.py
"""
Browser fingerprint handling and session ID generation.
"""

import uuid
import hashlib
from typing import Optional
from fastapi import Request


def get_fingerprint(request: Request) -> str:
    """
    Extract or generate fingerprint for a request.
    
    Priority:
    1. X-Fingerprint header (set by frontend JavaScript)
    2. X-Forwarded-For header (proxy/load balancer)
    3. Client IP address
    4. Generated from user agent + accept headers
    """
    # Check for explicit fingerprint
    fingerprint = request.headers.get("X-Fingerprint")
    if fingerprint:
        return fingerprint
    
    # Try forwarded IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        return f"ip:{ip}"
    
    # Use client IP
    if request.client and request.client.host:
        return f"ip:{request.client.host}"
    
    # Last resort: generate from headers
    user_agent = request.headers.get("User-Agent", "unknown")
    accept = request.headers.get("Accept", "")
    accept_lang = request.headers.get("Accept-Language", "")
    
    combined = f"{user_agent}:{accept}:{accept_lang}"
    return f"hash:{hashlib.md5(combined.encode()).hexdigest()}"


def generate_session_id() -> str:
    """
    Generate a unique session ID.
    """
    return str(uuid.uuid4())


def validate_fingerprint(fingerprint: str) -> bool:
    """
    Validate that a fingerprint looks legitimate.
    """
    if not fingerprint:
        return False
    
    # Must be non-empty string
    if not isinstance(fingerprint, str):
        return False
    
    # Reasonable length
    if len(fingerprint) < 8 or len(fingerprint) > 256:
        return False
    
    return True


def normalize_fingerprint(fingerprint: Optional[str], request: Request) -> str:
    """
    Normalize or generate a fingerprint.
    """
    if fingerprint and validate_fingerprint(fingerprint):
        return fingerprint
    
    return get_fingerprint(request)
