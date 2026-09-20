"""Integration tests for the clients router against the real FastAPI app."""
import pytest
from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import app

API_KEY = "test-key"
OPERATOR_KEY = "test-operator-key"
HEADERS = {"X-API-Key": API_KEY, "X-End-User-Id": "end-user-1"}
OPERATOR_HEADERS = {"X-API-Key": OPERATOR_KEY}
VALID_PAYLOAD = {
    "client_id": "1234567",
    "full_name": "Juan Perez",
    "phone": "3001234567",
    "email": "juan.perez@example.com",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TOOLS_API_KEY", API_KEY)
    monkeypatch.setenv("OPERATOR_API_KEY", OPERATOR_KEY)
    connection = init_db(tmp_path / "test.db")

    def override_get_db():
        yield connection

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    connection.close()


def test_get_unknown_client_returns_404_with_exists_false(client):
    response = client.get("/api/v1/clients/9999999", headers=HEADERS)
    assert response.status_code == 404
    assert response.json() == {"exists": False}


def test_post_creates_client_and_returns_201(client):
    response = client.post("/api/v1/clients", json=VALID_PAYLOAD, headers=HEADERS)
    assert response.status_code == 201
    assert response.json()["client"]["client_id"] == VALID_PAYLOAD["client_id"]


def test_get_existing_client_returns_200_with_client_data(client):
    client.post("/api/v1/clients", json=VALID_PAYLOAD, headers=HEADERS)
    response = client.get(f"/api/v1/clients/{VALID_PAYLOAD['client_id']}", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["exists"] is True
    assert body["client"]["full_name"] == VALID_PAYLOAD["full_name"]


def test_post_duplicate_client_returns_409(client):
    client.post("/api/v1/clients", json=VALID_PAYLOAD, headers=HEADERS)
    response = client.post("/api/v1/clients", json=VALID_PAYLOAD, headers=HEADERS)
    assert response.status_code == 409
    assert "error" in response.json()


def test_post_invalid_payload_returns_422_with_field_detail(client):
    bad_payload = {**VALID_PAYLOAD, "phone": "123"}
    response = client.post("/api/v1/clients", json=bad_payload, headers=HEADERS)
    assert response.status_code == 422
    body = response.json()
    assert any(error["field"] == "phone" for error in body["errors"])


def test_request_without_api_key_is_rejected(client):
    response = client.get(f"/api/v1/clients/{VALID_PAYLOAD['client_id']}")
    assert response.status_code == 401


def test_new_client_has_no_previous_memory(client):
    response = client.post("/api/v1/clients", json=VALID_PAYLOAD, headers=HEADERS)
    client_id = response.json()["client"]["client_id"]
    response = client.get(f"/api/v1/clients/{client_id}", headers=HEADERS)
    assert response.json()["previous_memory"] is None


def test_returning_client_sees_accumulated_memory_from_a_past_session(client):
    """A client mentions a budget and views a product before identifying, then identifies
    in a brand new session days later and should see that history without repeating it."""
    client_id = VALID_PAYLOAD["client_id"]

    # Session A: the client mentions a budget and a product before identifying.
    client.put(
        "/api/v1/sessions/session-a",
        json={"mentioned_budget": 5_000_000, "product_viewed": "laptop-a"},
        headers=HEADERS,
    )
    # Session A: the client identifies mid-conversation (registers as a new client).
    response = client.post(
        "/api/v1/clients?session_id=session-a", json=VALID_PAYLOAD, headers=HEADERS
    )
    assert response.status_code == 201

    # Session B (a brand new conversation, days later): the client identifies again.
    response = client.get(
        f"/api/v1/clients/{client_id}?session_id=session-b", headers=HEADERS
    )
    assert response.status_code == 200
    previous_memory = response.json()["previous_memory"]
    assert previous_memory["mentioned_budgets"] == [5_000_000]
    assert previous_memory["products_viewed"] == ["laptop-a"]

    # Session B mentions a new, higher budget; the old one is preserved, not overwritten.
    client.put(
        "/api/v1/sessions/session-b",
        json={"mentioned_budget": 6_000_000},
        headers=HEADERS,
    )
    response = client.get(
        f"/api/v1/clients/{client_id}?session_id=session-b", headers=HEADERS
    )
    assert response.json()["previous_memory"]["mentioned_budgets"] == [5_000_000, 6_000_000]


def test_history_endpoint_lists_current_memory_and_past_sessions(client):
    client_id = VALID_PAYLOAD["client_id"]
    client.put(
        "/api/v1/sessions/session-a",
        json={"mentioned_budget": 5_000_000},
        headers=HEADERS,
    )
    client.post("/api/v1/clients?session_id=session-a", json=VALID_PAYLOAD, headers=HEADERS)

    response = client.get(f"/api/v1/clients/{client_id}/history", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["current_memory"]["mentioned_budgets"] == [5_000_000]
    assert len(body["past_sessions"]) == 1
    assert body["past_sessions"][0]["session_id"] == "session-a"


def test_history_endpoint_for_unknown_client_has_no_memory_and_no_sessions(client):
    response = client.get("/api/v1/clients/9999999/history", headers=OPERATOR_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["current_memory"] is None
    assert body["past_sessions"] == []
