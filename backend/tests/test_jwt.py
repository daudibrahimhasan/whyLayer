import os
import pytest
from datetime import datetime, timezone
import jwt
from fastapi import HTTPException
from utils.jwt import create_access_token, verify_access_token

def test_create_and_verify_token():
    """Test that a JWT token can be created and successfully verified."""
    user_id = 99
    email = "test@whylayer.com"
    token = create_access_token(user_id=user_id, email=email)
    
    assert isinstance(token, str)
    
    payload = verify_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["email"] == email
    assert payload["is_guest"] is False

def test_verify_invalid_token():
    """Test that an invalid token raises the correct HTTPException."""
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI.eyJzdWIiOiIxMjMifQ.InvalidSignature"
    
    with pytest.raises(HTTPException) as excinfo:
        verify_access_token(invalid_token)
        
    assert excinfo.value.status_code == 401
    assert "Invalid authentication token" in excinfo.value.detail
