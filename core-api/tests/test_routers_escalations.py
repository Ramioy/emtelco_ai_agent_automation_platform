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


# --- reading tickets back -----------------------------------------------------------------

CAMILA = "1010101010"
CAMILA_ORDER = "order-002"
ANDRES = "2020202020"
ANDRES_ORDER = "order-005"
ANDRES_HEADERS = {"X-API-Key": API_KEY, "X-End-User-Id": "end-user-2"}


def identify(client, headers, client_id):
    response = client.get(f"/api/v1/clients/{client_id}", headers=headers)
    assert response.status_code == 200


def file_claim(client, headers, order_id, description):
    response = client.post(
        "/api/v1/warranty/claims",
        json={"order_id": order_id, "description": description},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["ticket_id"]


def test_my_tickets_requires_an_api_key(client):
    assert client.get("/api/v1/escalations/mine").status_code == 401


def test_my_tickets_is_refused_before_the_customer_has_identified(client):
    response = client.get("/api/v1/escalations/mine", headers=HEADERS)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_not_verified"


def test_my_tickets_is_refused_without_the_identity_header(client):
    response = client.get("/api/v1/escalations/mine", headers={"X-API-Key": API_KEY})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_required"


def test_my_tickets_is_empty_for_a_customer_who_has_raised_none(client):
    identify(client, HEADERS, CAMILA)
    response = client.get("/api/v1/escalations/mine", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == []


def test_a_warranty_claim_ticket_is_readable_by_the_number_given_to_the_customer(client):
    identify(client, HEADERS, CAMILA)
    ticket_id = file_claim(client, HEADERS, CAMILA_ORDER, "el televisor no enciende")

    tickets = client.get("/api/v1/escalations/mine", headers=HEADERS).json()
    ticket = next(item for item in tickets if item["ticket_id"] == ticket_id)
    assert ticket["origin"] == "warranty_claim"
    assert ticket["status"] == "pending_agent"
    assert ticket["topic"] == "el televisor no enciende"
    assert ticket["related_ticket_id"] is None


def test_a_ticket_raised_by_asking_for_a_person_is_readable_too(client):
    identify(client, HEADERS, CAMILA)
    created = client.post(
        "/api/v1/escalations",
        json={
            "session_id": "session-x",
            "reason": "El cliente pidio hablar con una persona",
            "priority": "medium",
        },
        headers=HEADERS,
    ).json()

    tickets = client.get("/api/v1/escalations/mine", headers=HEADERS).json()
    ticket = next(item for item in tickets if item["ticket_id"] == created["ticket_id"])
    assert ticket["origin"] == "agent_request"
    assert ticket["topic"] == "El cliente pidio hablar con una persona"


def test_my_tickets_never_returns_another_customers_ticket(client):
    identify(client, HEADERS, CAMILA)
    camila_ticket = file_claim(client, HEADERS, CAMILA_ORDER, "el televisor no enciende")
    identify(client, ANDRES_HEADERS, ANDRES)
    andres_ticket = file_claim(client, ANDRES_HEADERS, ANDRES_ORDER, "el equipo llego rayado")

    tickets = client.get("/api/v1/escalations/mine", headers=ANDRES_HEADERS).json()
    ticket_ids = {item["ticket_id"] for item in tickets}
    assert andres_ticket in ticket_ids
    assert camila_ticket not in ticket_ids


def test_my_tickets_withholds_the_assignee_the_note_and_the_priority(client):
    identify(client, HEADERS, CAMILA)
    ticket_id = file_claim(client, HEADERS, CAMILA_ORDER, "el televisor no enciende")
    client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "in_progress", "assignee": "Laura Restrepo"},
        headers=OPERATOR_HEADERS,
    )

    tickets = client.get("/api/v1/escalations/mine", headers=HEADERS).json()
    ticket = next(item for item in tickets if item["ticket_id"] == ticket_id)
    assert ticket["status"] == "in_progress"
    assert set(ticket) == {
        "ticket_id",
        "origin",
        "status",
        "topic",
        "created_at",
        "updated_at",
        "related_ticket_id",
    }


def test_my_tickets_shows_the_state_the_operations_console_left_the_ticket_in(client):
    identify(client, HEADERS, CAMILA)
    ticket_id = file_claim(client, HEADERS, CAMILA_ORDER, "el televisor no enciende")
    client.patch(
        f"/api/v1/escalations/{ticket_id}",
        json={"status": "resolved", "resolution_note": "Cambio de unidad autorizado"},
        headers=OPERATOR_HEADERS,
    )

    tickets = client.get("/api/v1/escalations/mine", headers=HEADERS).json()
    ticket = next(item for item in tickets if item["ticket_id"] == ticket_id)
    assert ticket["status"] == "resolved"


# --- linking the follow-up to the ticket it came from -------------------------------------


def test_escalating_about_an_existing_ticket_records_it_as_the_follow_up(client):
    identify(client, HEADERS, CAMILA)
    claim_ticket = file_claim(client, HEADERS, CAMILA_ORDER, "el televisor no enciende")
    follow_up = client.post(
        "/api/v1/escalations",
        json={
            "session_id": "session-x",
            "reason": "El cliente quiere hablar con una persona sobre su reclamo",
            "priority": "medium",
            "related_ticket_id": claim_ticket,
        },
        headers=HEADERS,
    )
    assert follow_up.status_code == 201

    tickets = client.get("/api/v1/escalations/mine", headers=HEADERS).json()
    ticket = next(
        item for item in tickets if item["ticket_id"] == follow_up.json()["ticket_id"]
    )
    assert ticket["related_ticket_id"] == claim_ticket


def test_an_empty_related_ticket_id_is_treated_as_none(client):
    identify(client, HEADERS, CAMILA)
    response = client.post(
        "/api/v1/escalations",
        json={
            "session_id": "session-x",
            "reason": "El cliente pidio hablar con una persona",
            "priority": "medium",
            "related_ticket_id": "   ",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    tickets = client.get("/api/v1/escalations/mine", headers=HEADERS).json()
    ticket = next(
        item for item in tickets if item["ticket_id"] == response.json()["ticket_id"]
    )
    assert ticket["related_ticket_id"] is None


def test_the_response_says_which_ticket_the_follow_up_was_attached_to(client):
    identify(client, HEADERS, CAMILA)
    claim_ticket = file_claim(client, HEADERS, CAMILA_ORDER, "el televisor no enciende")
    body = client.post(
        "/api/v1/escalations",
        json={
            "session_id": "session-x",
            "reason": "reason",
            "priority": "medium",
            "related_ticket_id": claim_ticket,
        },
        headers=HEADERS,
    ).json()
    assert body["related_ticket_id"] == claim_ticket


def test_an_unknown_ticket_number_drops_the_link_without_blocking_the_escalation(client):
    identify(client, HEADERS, CAMILA)
    response = client.post(
        "/api/v1/escalations",
        json={
            "session_id": "session-x",
            "reason": "reason",
            "priority": "medium",
            "related_ticket_id": "ticket-does-not-exist",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["related_ticket_id"] is None


def test_a_follow_up_cannot_be_hung_off_another_customers_ticket(client):
    identify(client, HEADERS, CAMILA)
    camila_ticket = file_claim(client, HEADERS, CAMILA_ORDER, "el televisor no enciende")
    identify(client, ANDRES_HEADERS, ANDRES)

    response = client.post(
        "/api/v1/escalations",
        json={
            "session_id": "session-y",
            "reason": "reason",
            "priority": "medium",
            "related_ticket_id": camila_ticket,
        },
        headers=ANDRES_HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["related_ticket_id"] is None

    listed = client.get("/api/v1/escalations", headers=OPERATOR_HEADERS).json()
    by_id = {item["ticket_id"]: item for item in listed}
    assert by_id[response.json()["ticket_id"]]["related_ticket_id"] is None


def test_a_follow_up_raised_before_identifying_carries_no_link(client):
    response = client.post(
        "/api/v1/escalations",
        json={
            "session_id": "session-z",
            "reason": "Quiero hablar con alguien",
            "priority": "medium",
            "related_ticket_id": "ticket-whatever",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["related_ticket_id"] is None


def test_the_operations_list_carries_the_link_between_the_two_numbers(client):
    identify(client, HEADERS, CAMILA)
    claim_ticket = file_claim(client, HEADERS, CAMILA_ORDER, "el televisor no enciende")
    follow_up = client.post(
        "/api/v1/escalations",
        json={
            "session_id": "session-x",
            "reason": "El cliente quiere hablar con una persona",
            "priority": "medium",
            "related_ticket_id": claim_ticket,
        },
        headers=HEADERS,
    ).json()

    listed = client.get("/api/v1/escalations", headers=OPERATOR_HEADERS).json()
    by_id = {item["ticket_id"]: item for item in listed}
    assert by_id[follow_up["ticket_id"]]["related_ticket_id"] == claim_ticket
    assert by_id[claim_ticket]["origin"] == "warranty_claim"

