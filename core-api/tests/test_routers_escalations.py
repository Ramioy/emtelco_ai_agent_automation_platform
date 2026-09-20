"""Integration tests for the escalations router against the real FastAPI app."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import app

API_KEY = "test-key"
OPERATOR_KEY = "test-operator-key"
HEADERS = {"X-API-Key": API_KEY, "X-End-User-Id": "end-user-1"}
OPERATOR_HEADERS = {"X-API-Key": OPERATOR_KEY}


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


def _open_ticket(client, reason="Customer asked for a person", priority="medium") -> str:
    response = client.post(
        "/api/v1/escalations",
        json={"session_id": "session-x", "reason": reason, "priority": priority},
        headers=HEADERS,
    )
    return response.json()["ticket_id"]


def _safety_ticket(client) -> str:
    """Raised the way the store raises it: a claim whose wording is a safety risk."""
    client.get("/api/v1/clients/1010101010", headers=HEADERS)
    client.post(
        "/api/v1/warranty/claims",
        json={"order_id": "order-001", "description": "el cargador echo humo y chispas"},
        headers=HEADERS,
    )
    tickets = client.get("/api/v1/escalations", headers=OPERATOR_HEADERS).json()
    return next(ticket["ticket_id"] for ticket in tickets if ticket["origin"] == "safety_risk")


def test_list_returns_every_ticket_with_its_origin_and_priority(client):
    _open_ticket(client)
    _safety_ticket(client)
    tickets = client.get("/api/v1/escalations", headers=OPERATOR_HEADERS).json()
    origins = {ticket["origin"] for ticket in tickets}
    assert origins == {"agent_request", "safety_risk"}
    assert all(ticket["status"] == "pending_agent" for ticket in tickets)


def test_list_is_reserved_for_the_operator_key(client):
    assert client.get("/api/v1/escalations", headers=HEADERS).status_code == 403
    assert client.get("/api/v1/escalations").status_code == 401


def test_an_agent_request_ticket_can_be_closed_straight_away_with_a_note(client):
    ticket_id = _open_ticket(client)
    response = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "resolved", "assignee": "Laura", "resolution_note": "Se llamo"},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["assignee"] == "Laura"
    assert body["resolution_note"] == "Se llamo"


def test_closing_a_ticket_without_a_note_is_refused(client):
    ticket_id = _open_ticket(client)
    response = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "resolved"},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "resolution_note_required"


def test_taking_a_ticket_without_a_name_is_refused(client):
    ticket_id = _open_ticket(client)
    response = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "in_progress"},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assignee_required"


def test_a_safety_ticket_cannot_be_closed_before_a_person_takes_it(client):
    ticket_id = _safety_ticket(client)
    response = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "resolved", "resolution_note": "Cerrado"},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "human_review_required"


def test_a_safety_ticket_closes_once_it_has_been_taken_and_has_a_note(client):
    ticket_id = _safety_ticket(client)
    taken = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "in_progress", "assignee": "Laura"},
        headers=OPERATOR_HEADERS,
    )
    assert taken.status_code == 200
    assert taken.json()["status"] == "in_progress"

    closed = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "resolved", "resolution_note": "Recogida coordinada"},
        headers=OPERATOR_HEADERS,
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "resolved"
    assert closed.json()["assignee"] == "Laura"


def test_a_safety_ticket_is_raised_with_high_priority(client):
    ticket_id = _safety_ticket(client)
    tickets = client.get("/api/v1/escalations", headers=OPERATOR_HEADERS).json()
    ticket = next(item for item in tickets if item["ticket_id"] == ticket_id)
    assert ticket["priority"] == "high"


def test_a_resolved_ticket_can_be_reopened_but_not_resolved_again(client):
    ticket_id = _open_ticket(client)
    client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "resolved", "assignee": "Laura", "resolution_note": "Se llamo"},
        headers=OPERATOR_HEADERS,
    )
    again = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "resolved", "resolution_note": "otra vez"},
        headers=OPERATOR_HEADERS,
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_transition"

    reopened = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "in_progress"},
        headers=OPERATOR_HEADERS,
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "in_progress"


def test_a_ticket_cannot_go_back_to_pending(client):
    ticket_id = _open_ticket(client)
    client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "in_progress", "assignee": "Laura"},
        headers=OPERATOR_HEADERS,
    )
    response = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "pending_agent"},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 409


def test_an_unknown_status_is_rejected_before_any_lifecycle_rule(client):
    ticket_id = _open_ticket(client)
    response = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "cerrado"},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 422


def test_updating_an_unknown_ticket_returns_404(client):
    response = client.patch(
        "/api/v1/escalations/ticket-does-not-exist",
        json={"status": "in_progress", "assignee": "Laura"},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 404


def test_the_agent_key_cannot_move_a_ticket(client):
    ticket_id = _open_ticket(client)
    response = client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "in_progress", "assignee": "Laura"},
        headers=HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "operator_only"
