import os
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_root_endpoint():
    """Test the root info endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert "name" in response.json()
    assert response.json()["name"] == "whyLayer Decision Intelligence Engine"
