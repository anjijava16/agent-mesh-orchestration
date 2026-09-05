from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    # No lifespan: these tests exercise routing and validation, not dependencies.
    return TestClient(app)


def test_root_advertises_the_default_framework(client):
    body = client.get("/").json()
    assert body["default_framework"] in {"google_adk", "langgraph", "deepagents", "claude_agent_sdk"}


def test_liveness_never_touches_a_dependency(client):
    assert client.get("/api/v1/health/live").json()["status"] == "alive"


def test_frameworks_endpoint_lists_all_four(client):
    frameworks = client.get("/api/v1/frameworks").json()["frameworks"]
    assert {f["id"] for f in frameworks} == {"google_adk", "langgraph", "deepagents", "claude_agent_sdk"}


def test_empty_message_is_rejected(client):
    response = client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_unknown_framework_is_rejected(client):
    response = client.post("/api/v1/chat", json={"message": "hi", "framework": "autogen"})
    assert response.status_code == 422
