import os
import pytest

# Set default env vars for all pytest tests
os.environ["JWT_SECRET_KEY"] = "test-secret-key-123"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["JWT_EXPIRE_MINUTES"] = "60"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000"
