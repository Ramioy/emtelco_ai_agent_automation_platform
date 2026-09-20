"""Integration tests for per-user isolation: the boundary is the microservice, not the prompt."""
import pytest
from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import app

API_KEY = "test-key"
OPERATOR_KEY = "test-operator-key"

CAMILA = "1010101010"
ANDRES = "2020202020"
CAMILA_ORDER = "order-001"
ANDRES_ORDER = "order-005"

OPERATOR_HEADERS = {"X-API-Key": OPERATOR_KEY}


def agent_headers(subject: str | None = "end-user-1") -> dict:
    headers = {"X-API-Key": API_KEY}
    if subject is not None:
        headers["X-End-User-Id"] = subject
    return headers


@pytest.fixture
def db_connection(tmp_path):
    connection = init_db(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def client(db_connection, monkeypatch):
    monkeypatch.setenv("TOOLS_API_KEY", API_KEY)
    monkeypatch.setenv("OPERATOR_API_KEY", OPERATOR_KEY)
    monkeypatch.delenv("IDENTITY_ISOLATION", raising=False)
    monkeypatch.delenv("IDENTITY_REBINDING", raising=False)

    def override_get_db():
        yield db_connection

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def identify(client, subject: str, client_id: str):
    return client.get(f"/api/v1/clients/{client_id}", headers=agent_headers(subject))


# --- no identity at all -----------------------------------------------------------------


def test_client_lookup_without_the_identity_header_is_refused(client):
    response = client.get(f"/api/v1/clients/{CAMILA}", headers=agent_headers(None))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_required"


def test_an_empty_identity_header_counts_as_no_identity(client):
    response = client.get(f"/api/v1/clients/{CAMILA}", headers=agent_headers("   "))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_required"


def test_order_status_without_the_identity_header_is_refused(client):
    response = client.get(
        f"/api/v1/orders/{CAMILA_ORDER}/status", headers=agent_headers(None)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_required"


def test_the_catalog_needs_no_identity_because_it_is_not_customer_data(client):
    response = client.get("/api/v1/catalog/products", headers=agent_headers(None))
    assert response.status_code == 200


# --- binding on first identification ----------------------------------------------------


def test_first_identification_binds_the_end_user_and_lets_them_see_their_own_data(client):
    assert identify(client, "user-a", CAMILA).status_code == 200
    response = client.get(
        f"/api/v1/orders/{CAMILA_ORDER}/status", headers=agent_headers("user-a")
    )
    assert response.status_code == 200
    assert response.json()["order_id"] == CAMILA_ORDER


def test_a_bound_end_user_claiming_another_identification_number_is_refused(client):
    identify(client, "user-a", CAMILA)
    response = identify(client, "user-a", ANDRES)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_mismatch"


def test_a_bound_end_user_cannot_read_another_customers_order(client):
    identify(client, "user-a", CAMILA)
    response = client.get(
        f"/api/v1/orders/{ANDRES_ORDER}/status", headers=agent_headers("user-a")
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_mismatch"


def test_a_bound_end_user_cannot_read_another_customers_eta_or_move_their_address(client):
    identify(client, "user-a", CAMILA)
    assert (
        client.get(
            f"/api/v1/orders/{ANDRES_ORDER}/eta", headers=agent_headers("user-a")
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/orders/{ANDRES_ORDER}/address",
            json={"delivery_address": "Calle Falsa 123"},
            headers=agent_headers("user-a"),
        ).status_code
        == 403
    )


def test_a_bound_end_user_cannot_read_another_customers_history(client):
    identify(client, "user-a", CAMILA)
    response = client.get(f"/api/v1/clients/{ANDRES}/history", headers=agent_headers("user-a"))
    assert response.status_code == 403


def test_a_bound_end_user_cannot_check_another_customers_warranty(client):
    identify(client, "user-a", CAMILA)
    response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": ANDRES_ORDER, "product_id": "smartphone-001"},
        headers=agent_headers("user-a"),
    )
    assert response.status_code == 403


def test_a_bound_end_user_cannot_file_a_claim_on_another_customers_order(client):
    identify(client, "user-a", CAMILA)
    response = client.post(
        "/api/v1/warranty/claims",
        json={"order_id": ANDRES_ORDER, "description": "no enciende"},
        headers=agent_headers("user-a"),
    )
    assert response.status_code == 403


def test_two_different_end_users_stay_on_their_own_customers(client):
    identify(client, "user-a", CAMILA)
    identify(client, "user-b", ANDRES)
    assert (
        client.get(
            f"/api/v1/orders/{ANDRES_ORDER}/status", headers=agent_headers("user-b")
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/orders/{CAMILA_ORDER}/status", headers=agent_headers("user-b")
        ).status_code
        == 403
    )


def test_identifying_an_unregistered_number_does_not_burn_the_binding(client):
    assert client.get("/api/v1/clients/9999999", headers=agent_headers("user-a")).status_code == 404
    assert identify(client, "user-a", CAMILA).status_code == 200


def test_registering_binds_the_end_user_to_the_new_customer(client):
    payload = {
        "client_id": "1234567",
        "full_name": "Juan Perez",
        "phone": "3001234567",
        "email": "juan.perez@example.com",
    }
    assert client.post("/api/v1/clients", json=payload, headers=agent_headers("user-new")).status_code == 201
    response = client.get("/api/v1/orders/mine", headers=agent_headers("user-new"))
    assert response.status_code == 200
    assert response.json() == []


def test_a_bound_end_user_cannot_register_a_second_person_onto_themselves(client):
    identify(client, "user-a", CAMILA)
    payload = {
        "client_id": "1234567",
        "full_name": "Juan Perez",
        "phone": "3001234567",
        "email": "juan.perez@example.com",
    }
    response = client.post("/api/v1/clients", json=payload, headers=agent_headers("user-a"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_mismatch"


# --- client_id derived instead of supplied ----------------------------------------------


def test_listing_my_orders_needs_no_identification_number_at_all(client):
    identify(client, "user-a", CAMILA)
    response = client.get("/api/v1/orders/mine", headers=agent_headers("user-a"))
    assert response.status_code == 200
    assert {order["order_id"] for order in response.json()} == {
        "order-001",
        "order-002",
        "order-003",
        "order-004",
    }


def test_listing_my_orders_before_identifying_is_refused(client):
    response = client.get("/api/v1/orders/mine", headers=agent_headers("user-a"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_not_verified"


def test_creating_an_order_uses_the_bound_customer_when_none_is_sent(client):
    identify(client, "user-a", CAMILA)
    response = client.post(
        "/api/v1/orders",
        json={"product_id": "laptop-001", "delivery_address": "Calle Nueva 1"},
        headers=agent_headers("user-a"),
    )
    assert response.status_code == 201
    orders = client.get("/api/v1/orders/mine", headers=agent_headers("user-a")).json()
    assert response.json()["order_id"] in {order["order_id"] for order in orders}


def test_creating_an_order_for_somebody_else_is_refused_even_if_the_body_says_so(client):
    identify(client, "user-a", CAMILA)
    response = client.post(
        "/api/v1/orders",
        json={
            "client_id": ANDRES,
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=agent_headers("user-a"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_mismatch"


def test_creating_an_order_before_identifying_is_refused(client):
    response = client.post(
        "/api/v1/orders",
        json={"product_id": "laptop-001", "delivery_address": "Calle Nueva 1"},
        headers=agent_headers("user-a"),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_not_verified"


def test_a_claim_is_filed_for_the_bound_customer_without_being_told_who_that_is(client):
    identify(client, "user-a", CAMILA)
    response = client.post(
        "/api/v1/warranty/claims",
        json={"order_id": CAMILA_ORDER, "description": "la pantalla no enciende"},
        headers=agent_headers("user-a"),
    )
    assert response.status_code == 201
    tickets = client.get("/api/v1/escalations", headers=OPERATOR_HEADERS).json()
    assert all(ticket["client_id"] in (None, CAMILA) for ticket in tickets)


def test_a_claim_with_a_borrowed_identification_number_in_the_body_is_refused(client):
    identify(client, "user-a", CAMILA)
    response = client.post(
        "/api/v1/warranty/claims",
        json={"order_id": CAMILA_ORDER, "description": "falla", "client_id": ANDRES},
        headers=agent_headers("user-a"),
    )
    assert response.status_code == 403


# --- the operator principal -------------------------------------------------------------


def test_the_operator_key_reaches_the_list_endpoints_and_the_agent_key_does_not(client):
    identify(client, "user-a", CAMILA)
    assert client.get("/api/v1/orders", headers=agent_headers("user-a")).status_code == 403
    assert client.get("/api/v1/warranty", headers=agent_headers("user-a")).status_code == 403
    assert client.get("/api/v1/escalations", headers=agent_headers("user-a")).status_code == 403
    assert client.get("/api/v1/orders", headers=OPERATOR_HEADERS).status_code == 200
    assert client.get("/api/v1/warranty", headers=OPERATOR_HEADERS).status_code == 200
    assert client.get("/api/v1/escalations", headers=OPERATOR_HEADERS).status_code == 200


def test_the_agent_key_cannot_list_another_customers_orders_by_number(client):
    identify(client, "user-a", CAMILA)
    response = client.get(
        f"/api/v1/orders/by-client/{ANDRES}", headers=agent_headers("user-a")
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "operator_only"


def test_the_operator_key_is_never_bound_to_a_customer(client):
    assert client.get(f"/api/v1/clients/{CAMILA}", headers=OPERATOR_HEADERS).status_code == 200
    assert client.get(f"/api/v1/clients/{ANDRES}", headers=OPERATOR_HEADERS).status_code == 200
    assert client.get(f"/api/v1/orders/by-client/{ANDRES}", headers=OPERATOR_HEADERS).status_code == 200


def test_the_operator_key_is_rejected_where_a_wrong_key_would_be(client):
    assert client.get("/api/v1/orders", headers={"X-API-Key": "nope"}).status_code == 401


# --- the two configured modes -----------------------------------------------------------


def test_rebinding_is_denied_by_default_and_allowed_when_configured(client, monkeypatch):
    identify(client, "user-a", CAMILA)
    assert identify(client, "user-a", ANDRES).status_code == 403

    monkeypatch.setenv("IDENTITY_REBINDING", "allowed")
    assert identify(client, "user-a", ANDRES).status_code == 200
    assert (
        client.get(
            f"/api/v1/orders/{ANDRES_ORDER}/status", headers=agent_headers("user-a")
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/orders/{CAMILA_ORDER}/status", headers=agent_headers("user-a")
        ).status_code
        == 403
    )


def test_isolation_disabled_restores_the_unguarded_behaviour(client, monkeypatch):
    monkeypatch.setenv("IDENTITY_ISOLATION", "disabled")
    assert client.get(f"/api/v1/clients/{CAMILA}", headers=agent_headers(None)).status_code == 200
    assert client.get(f"/api/v1/clients/{ANDRES}", headers=agent_headers(None)).status_code == 200
    assert (
        client.get(
            f"/api/v1/orders/{ANDRES_ORDER}/status", headers=agent_headers(None)
        ).status_code
        == 200
    )


def test_a_misspelled_isolation_value_leaves_the_boundary_on(client, monkeypatch):
    monkeypatch.setenv("IDENTITY_ISOLATION", "enforcedd")
    assert client.get(f"/api/v1/clients/{CAMILA}", headers=agent_headers(None)).status_code == 403


def test_health_announces_which_mode_is_active(client, monkeypatch):
    body = client.get("/health").json()
    assert body == {
        "status": "ok",
        "identity_isolation": "enforced",
        "identity_rebinding": "denied",
    }

    monkeypatch.setenv("IDENTITY_ISOLATION", "disabled")
    assert client.get("/health").json()["identity_isolation"] == "disabled"


# --- session memory ---------------------------------------------------------------------


def test_an_identified_session_is_readable_only_by_the_end_user_it_belongs_to(client):
    identify(client, "user-a", CAMILA)
    client.get(
        f"/api/v1/clients/{CAMILA}",
        params={"session_id": "session-camila"},
        headers=agent_headers("user-a"),
    )
    assert (
        client.get(
            "/api/v1/sessions/session-camila", headers=agent_headers("user-a")
        ).status_code
        == 200
    )

    identify(client, "user-b", ANDRES)
    response = client.get("/api/v1/sessions/session-camila", headers=agent_headers("user-b"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity_mismatch"


def test_an_identified_session_cannot_be_overwritten_by_another_end_user(client):
    identify(client, "user-a", CAMILA)
    client.get(
        f"/api/v1/clients/{CAMILA}",
        params={"session_id": "session-camila"},
        headers=agent_headers("user-a"),
    )
    identify(client, "user-b", ANDRES)
    response = client.put(
        "/api/v1/sessions/session-camila",
        json={"client_name": "Otro Nombre"},
        headers=agent_headers("user-b"),
    )
    assert response.status_code == 403
    session = client.get(
        "/api/v1/sessions/session-camila", headers=agent_headers("user-a")
    ).json()
    assert session["client_name"] != "Otro Nombre"


def test_a_session_nobody_has_identified_in_is_still_open_scratch_state(client):
    response = client.get("/api/v1/sessions/session-anonymous", headers=agent_headers("user-a"))
    assert response.status_code == 200
    assert response.json()["client_id"] is None


def test_a_warranty_status_check_on_an_unknown_order_is_refused_not_answered(client):
    identify(client, "user-a", CAMILA)
    response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": "order-does-not-exist", "product_id": "laptop-001"},
        headers=agent_headers("user-a"),
    )
    assert response.status_code == 404
    assert response.json() == {"exists": False}


def test_a_claim_on_an_unknown_order_is_refused(client):
    identify(client, "user-a", CAMILA)
    response = client.post(
        "/api/v1/warranty/claims",
        json={"order_id": "order-does-not-exist", "description": "falla"},
        headers=agent_headers("user-a"),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_a_blank_assignee_does_not_count_as_a_person_taking_a_ticket(client):
    created = client.post(
        "/api/v1/escalations",
        json={"session_id": "session-x", "reason": "quiere una persona", "priority": "low"},
        headers=agent_headers("user-a"),
    ).json()
    response = client.patch(
        f"/api/v1/escalations/{created['ticket_id']}",
        json={"status": "in_progress", "assignee": "   "},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "assignee_required"
