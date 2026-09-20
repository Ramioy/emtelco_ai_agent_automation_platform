"""Integration tests for the escalations router against the real FastAPI app."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import app

API_KEY = "test-key"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TOOLS_API_KEY", API_KEY)
    connection = init_db(tmp_path / "test.db")

    def override_get_db():
        yield connection

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    connection.close()


def test_create_escalation_returns_201_ticket_id_and_pending_agent_status(client):
    response = client.post(
        "/api/v1/escalations",
        json={
            "session_id": "session-x",
            "reason": "Customer explicitly asked to speak with a human",
            "priority": "medium",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending_agent"
    assert "ticket_id" in body and body["ticket_id"]


def test_create_escalation_generates_a_different_ticket_id_each_time(client):
    payload = {"session_id": "session-x", "reason": "frustration", "priority": "medium"}
    first = client.post("/api/v1/escalations", json=payload, headers=HEADERS).json()
    second = client.post("/api/v1/escalations", json=payload, headers=HEADERS).json()
    assert first["ticket_id"] != second["ticket_id"]


def test_create_escalation_requires_api_key(client):
    response = client.post(
        "/api/v1/escalations",
        json={"session_id": "session-x", "reason": "x", "priority": "medium"},
    )
    assert response.status_code == 401


def test_create_escalation_fills_client_id_when_session_already_identified(client, tmp_path):
    # Links a seeded demo client to the session, via GET /clients/{id}?session_id=.
    client.get("/api/v1/clients/1010101010", params={"session_id": "session-y"}, headers=HEADERS)

    response = client.post(
        "/api/v1/escalations",
        json={"session_id": "session-y", "reason": "frustration", "priority": "medium"},
        headers=HEADERS,
    )
    body = response.json()

    connection = sqlite3.connect(tmp_path / "test.db")
    row = connection.execute(
        "SELECT client_id FROM escalations WHERE ticket_id = ?", (body["ticket_id"],)
    ).fetchone()
    connection.close()
    assert row == ("1010101010",)


def test_create_escalation_leaves_client_id_null_when_session_not_identified(client, tmp_path):
    response = client.post(
        "/api/v1/escalations",
        json={"session_id": "session-z", "reason": "frustration", "priority": "medium"},
        headers=HEADERS,
    )
    body = response.json()

    connection = sqlite3.connect(tmp_path / "test.db")
    row = connection.execute(
        "SELECT client_id FROM escalations WHERE ticket_id = ?", (body["ticket_id"],)
    ).fetchone()
    connection.close()
    assert row == (None,)
