import pytest
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)

def test_api_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] in ("health-insurance-knowledge-base", "healthshield-ai-voice-agent")
    assert data["indexed_records"] > 0

def test_api_search_grounded_query():
    payload = {
        "query": "What are the coverage benefits of the HealthShield Gold Plan?",
        "top_k": 3
    }
    response = client.post("/api/v1/kb/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["grounded_answer_available"] is True
    assert data["total_found"] > 0
    assert data["top_citation"] is not None
    assert len(data["results"]) <= 3

def test_api_search_out_of_scope_query():
    payload = {
        "query": "What is the pet insurance vaccination schedule for Golden Retrievers?",
        "top_k": 3
    }
    response = client.post("/api/v1/kb/search", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["grounded_answer_available"] is False
    assert data["total_found"] == 0
    assert data["top_citation"] is None
    assert "Information unavailable" in (data["fallback_message"] or "")

def test_api_voice_context_endpoint():
    payload = {
        "query": "Can someone aged 62 with hypertension get covered?"
    }
    response = client.post("/api/v1/kb/voice-context", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "query" in data
    assert "context" in data
    assert "STATUS: GROUNDED_INFO_FOUND" in data["context"]
    assert "[RECORD:" in data["context"]

def test_api_get_record_by_id():
    response = client.get("/api/v1/kb/records/kb_product_001")
    assert response.status_code == 200
    data = response.json()
    assert data["record_id"] == "kb_product_001"
    assert data["category"] == "product_info"
    assert data["source"].startswith("sample_product_brochure.html")

def test_api_get_record_not_found():
    response = client.get("/api/v1/kb/records/non_existent_record_id")
    assert response.status_code == 404
