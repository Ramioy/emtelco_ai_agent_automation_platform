"""Integration tests for the warranty router against the real FastAPI app."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import app
from app.repositories import warranty as warranty_repo

API_KEY = "test-key"
OPERATOR_KEY = "test-operator-key"
# The fixture identifies this end user as the seeded client who owns the seeded orders.
HEADERS = {"X-API-Key": API_KEY, "X-End-User-Id": "end-user-1"}
OPERATOR_HEADERS = {"X-API-Key": OPERATOR_KEY}
OWNER_CLIENT_ID = "1010101010"


@pytest.fixture
def db_connection(tmp_path):
    connection = init_db(tmp_path / "test.db")
    yield connection
    connection.close()


@pytest.fixture
def client(db_connection, monkeypatch):
    monkeypatch.setenv("TOOLS_API_KEY", API_KEY)
    monkeypatch.setenv("OPERATOR_API_KEY", OPERATOR_KEY)

    def override_get_db():
        yield db_connection

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    test_client.get(f"/api/v1/clients/{OWNER_CLIENT_ID}", headers=HEADERS)
    yield test_client
    app.dependency_overrides.clear()


def _warranties_by_id(client):
    response = client.get("/api/v1/warranty", headers=OPERATOR_HEADERS)
    return {warranty["warranty_id"]: warranty for warranty in response.json()}


def test_get_status_for_a_valid_warranty_returns_200_is_valid_true(client):
    response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": "order-002", "product_id": "headphones-001"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is True


def test_get_status_for_an_expired_warranty_returns_200_is_valid_false(client):
    response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": "order-003", "product_id": "tablet-001"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is False


def test_get_status_for_no_warranty_registered_returns_404_exists_false(client):
    response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": "order-001", "product_id": "laptop-002"},
        headers=HEADERS,
    )
    assert response.status_code == 404
    assert response.json() == {"exists": False}


def test_get_status_requires_api_key(client):
    response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": "order-002", "product_id": "headphones-001"},
    )
    assert response.status_code == 401


def test_terminate_sets_coverage_to_zero_and_a_later_status_check_is_expired(client):
    response = client.patch("/api/v1/warranty/warranty-001/terminate", headers=OPERATOR_HEADERS)
    assert response.status_code == 200
    assert response.json() == {
        "warranty_id": "warranty-001",
        "is_valid": False,
        "coverage_months": 0,
        "purchase_date": "2026-07-01",
        "months_remaining": 0,
    }

    status_response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": "order-002", "product_id": "headphones-001"},
        headers=HEADERS,
    )
    assert status_response.json()["is_valid"] is False


def test_terminate_for_unknown_warranty_id_returns_404(client):
    response = client.patch("/api/v1/warranty/does-not-exist/terminate", headers=OPERATOR_HEADERS)
    assert response.status_code == 404
    assert "error" in response.json()


def test_reinstate_brings_a_terminated_warranty_back_and_status_says_valid(client):
    client.patch("/api/v1/warranty/warranty-001/terminate", headers=OPERATOR_HEADERS)

    response = client.patch("/api/v1/warranty/warranty-001/reinstate", headers=OPERATOR_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["warranty_id"] == "warranty-001"
    assert body["is_valid"] is True
    assert body["months_remaining"] == warranty_repo.REINSTATED_MONTHS_REMAINING

    status_response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": "order-002", "product_id": "headphones-001"},
        headers=HEADERS,
    )
    assert status_response.json()["is_valid"] is True


def test_reinstate_revives_a_warranty_that_expired_on_its_own_without_moving_the_purchase_date(
    client,
):
    before = _warranties_by_id(client)["warranty-002"]
    assert before["is_valid"] is False

    response = client.patch("/api/v1/warranty/warranty-002/reinstate", headers=OPERATOR_HEADERS)
    assert response.status_code == 200
    assert response.json()["is_valid"] is True

    after = _warranties_by_id(client)["warranty-002"]
    assert after["purchase_date"] == before["purchase_date"]
    assert after["coverage_months"] > before["coverage_months"]


def test_reinstate_is_idempotent_and_a_second_call_leaves_the_same_state(client):
    first = client.patch("/api/v1/warranty/warranty-002/reinstate", headers=OPERATOR_HEADERS).json()
    second = client.patch("/api/v1/warranty/warranty-002/reinstate", headers=OPERATOR_HEADERS).json()
    assert first == second


def test_reinstate_for_unknown_warranty_id_returns_404(client):
    response = client.patch("/api/v1/warranty/does-not-exist/reinstate", headers=OPERATOR_HEADERS)
    assert response.status_code == 404
    assert "error" in response.json()


def test_reinstate_requires_api_key(client):
    assert client.patch("/api/v1/warranty/warranty-001/reinstate").status_code == 401


def test_create_claim_with_risk_keyword_returns_escalated_true_and_creates_escalation(
    client, tmp_path
):
    response = client.post(
        "/api/v1/warranty/claims",
        json={
            "order_id": "order-002",
            "description": "sale humo del televisor",
            "client_id": "1010101010",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["escalated"] is True
    assert body["status"] == "registered"
    assert "ticket_id" in body

    connection = sqlite3.connect(tmp_path / "test.db")
    row = connection.execute(
        "SELECT priority, status FROM escalations WHERE ticket_id = ?", (body["ticket_id"],)
    ).fetchone()
    connection.close()
    assert row == ("high", "pending_agent")


def test_create_claim_with_neutral_description_does_not_create_an_escalation(
    client, tmp_path
):
    response = client.post(
        "/api/v1/warranty/claims",
        json={
            "order_id": "order-002",
            "description": "el televisor no enciende",
            "client_id": "1010101010",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["escalated"] is False
    assert "ticket_id" in body

    connection = sqlite3.connect(tmp_path / "test.db")
    row = connection.execute(
        "SELECT 1 FROM escalations WHERE ticket_id = ?", (body["ticket_id"],)
    ).fetchone()
    connection.close()
    assert row is None


def test_create_claim_resolves_warranty_id_from_the_order(client, tmp_path):
    response = client.post(
        "/api/v1/warranty/claims",
        json={
            "order_id": "order-002",
            "description": "el televisor no enciende",
            "client_id": "1010101010",
        },
        headers=HEADERS,
    )
    body = response.json()

    connection = sqlite3.connect(tmp_path / "test.db")
    row = connection.execute(
        "SELECT warranty_id FROM warranty_claims WHERE claim_id = ?", (body["claim_id"],)
    ).fetchone()
    connection.close()
    assert row == ("warranty-001",)


def test_create_claim_for_an_order_without_a_warranty_still_succeeds(client, tmp_path):
    response = client.post(
        "/api/v1/warranty/claims",
        json={
            "order_id": "order-001",
            "description": "el laptop no prende",
            "client_id": "1010101010",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    body = response.json()

    connection = sqlite3.connect(tmp_path / "test.db")
    row = connection.execute(
        "SELECT warranty_id FROM warranty_claims WHERE claim_id = ?", (body["claim_id"],)
    ).fetchone()
    connection.close()
    assert row == (None,)


def test_create_claim_with_session_id_links_the_escalation_to_that_session(client, tmp_path):
    response = client.post(
        "/api/v1/warranty/claims",
        params={"session_id": "session-x"},
        json={
            "order_id": "order-002",
            "description": "sale chispa del cargador",
            "client_id": "1010101010",
        },
        headers=HEADERS,
    )
    body = response.json()

    connection = sqlite3.connect(tmp_path / "test.db")
    row = connection.execute(
        "SELECT session_id FROM escalations WHERE ticket_id = ?", (body["ticket_id"],)
    ).fetchone()
    connection.close()
    assert row == ("session-x",)


def test_create_claim_without_session_id_creates_an_escalation_with_no_session(client, tmp_path):
    response = client.post(
        "/api/v1/warranty/claims",
        json={
            "order_id": "order-002",
            "description": "sale chispa del cargador",
            "client_id": "1010101010",
        },
        headers=HEADERS,
    )
    body = response.json()

    connection = sqlite3.connect(tmp_path / "test.db")
    row = connection.execute(
        "SELECT session_id FROM escalations WHERE ticket_id = ?", (body["ticket_id"],)
    ).fetchone()
    connection.close()
    assert row == (None,)


def test_create_claim_requires_api_key(client):
    response = client.post(
        "/api/v1/warranty/claims",
        json={"order_id": "order-002", "description": "x", "client_id": "1010101010"},
    )
    assert response.status_code == 401


def test_list_warranties_returns_each_one_with_its_product_name_and_validity(client):
    assert client.get("/api/v1/warranty", headers=OPERATOR_HEADERS).status_code == 200
    body = _warranties_by_id(client)
    assert body["warranty-001"]["order_id"] == "order-002"
    assert body["warranty-001"]["product_name"] == "SoundWave ANC"
    assert body["warranty-001"]["coverage_months"] == 36
    assert body["warranty-001"]["is_valid"] is True
    assert body["warranty-002"]["product_name"] == "TabPro 11"
    assert body["warranty-002"]["is_valid"] is False


def test_list_warranties_reflects_a_termination(client):
    client.patch("/api/v1/warranty/warranty-001/terminate", headers=OPERATOR_HEADERS)
    body = _warranties_by_id(client)
    assert body["warranty-001"]["is_valid"] is False
    assert body["warranty-001"]["coverage_months"] == 0


def test_list_warranties_leaves_product_name_null_when_the_product_left_the_catalog(
    client, db_connection
):
    db_connection.execute("DELETE FROM products WHERE id = ?", ("headphones-001",))
    body = _warranties_by_id(client)
    assert body["warranty-001"]["product_id"] == "headphones-001"
    assert body["warranty-001"]["product_name"] is None


def test_list_warranties_requires_api_key(client):
    assert client.get("/api/v1/warranty").status_code == 401


def test_update_sets_coverage_and_purchase_date_and_recomputes_validity(client):
    response = client.patch(
        "/api/v1/warranty/warranty-002",
        json={"coverage_months": 36, "purchase_date": "2026-01-15"},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["coverage_months"] == 36
    assert body["purchase_date"] == "2026-01-15"
    assert body["is_valid"] is True


def test_update_accepts_only_one_field_and_leaves_the_other_untouched(client):
    before = _warranties_by_id(client)["warranty-001"]
    response = client.patch(
        "/api/v1/warranty/warranty-001", json={"coverage_months": 1}, headers=OPERATOR_HEADERS
    )
    assert response.status_code == 200
    assert response.json()["purchase_date"] == before["purchase_date"]
    assert response.json()["coverage_months"] == 1


def test_update_can_stage_an_expired_case_by_moving_the_purchase_date_back(client):
    response = client.patch(
        "/api/v1/warranty/warranty-001",
        json={"purchase_date": "2010-01-01"},
        headers=OPERATOR_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is False


def test_update_rejects_a_malformed_purchase_date(client):
    response = client.patch(
        "/api/v1/warranty/warranty-001", json={"purchase_date": "ayer"}, headers=OPERATOR_HEADERS
    )
    assert response.status_code == 422


def test_update_rejects_a_negative_coverage(client):
    response = client.patch(
        "/api/v1/warranty/warranty-001", json={"coverage_months": -1}, headers=OPERATOR_HEADERS
    )
    assert response.status_code == 422


def test_update_for_unknown_warranty_id_returns_404(client):
    response = client.patch(
        "/api/v1/warranty/does-not-exist", json={"coverage_months": 6}, headers=OPERATOR_HEADERS
    )
    assert response.status_code == 404
    assert "error" in response.json()


def test_update_requires_api_key(client):
    response = client.patch("/api/v1/warranty/warranty-001", json={"coverage_months": 6})
    assert response.status_code == 401


def test_the_seeded_order_left_without_a_warranty_still_reports_not_registered(client):
    response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": "order-001", "product_id": "laptop-002"},
        headers=HEADERS,
    )
    assert response.status_code == 404
    assert response.json() == {"exists": False}


def test_terminate_expires_a_warranty_issued_today_by_the_order_the_agent_took(client):
    order_id = client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    ).json()["order_id"]
    warranty_id = next(
        item["warranty_id"]
        for item in client.get("/api/v1/warranty", headers=OPERATOR_HEADERS).json()
        if item["order_id"] == order_id
    )

    response = client.patch(f"/api/v1/warranty/{warranty_id}/terminate", headers=OPERATOR_HEADERS)
    assert response.json()["is_valid"] is False

    status_response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": order_id, "product_id": "laptop-001"},
        headers=HEADERS,
    )
    assert status_response.json()["is_valid"] is False


def test_a_warranty_issued_today_survives_a_full_terminate_reinstate_round_trip(client):
    order_id = client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    ).json()["order_id"]
    warranty_id = next(
        item["warranty_id"]
        for item in client.get("/api/v1/warranty", headers=OPERATOR_HEADERS).json()
        if item["order_id"] == order_id
    )

    assert client.patch(
        f"/api/v1/warranty/{warranty_id}/terminate", headers=OPERATOR_HEADERS
    ).json()["is_valid"] is False
    assert client.patch(
        f"/api/v1/warranty/{warranty_id}/reinstate", headers=OPERATOR_HEADERS
    ).json()["is_valid"] is True
    assert client.patch(
        f"/api/v1/warranty/{warranty_id}/terminate", headers=OPERATOR_HEADERS
    ).json()["is_valid"] is False
