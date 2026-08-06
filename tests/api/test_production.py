import pytest
from fastapi.testclient import TestClient

from quantmind.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_disclaimer(client):
    resp = client.get("/api/disclaimer")
    assert resp.status_code == 200
    assert "educational" in resp.json()["text"].lower()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_chat_requires_no_auth_by_default(client):
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert "events" in resp.json()


def test_audit_query(client):
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    resp = client.post("/api/audit/query", json={"session_id": session_id, "limit": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(row["action"] in ("chat", "audit_query") for row in data)


def test_rate_limit_bypassed_in_tests(client):
    for _ in range(5):
        resp = client.get("/health")
        assert resp.status_code == 200
