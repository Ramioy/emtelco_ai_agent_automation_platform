"""Integration tests for the warranty router against the real FastAPI app."""
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
    response = client.patch("/api/v1/warranty/warranty-001/terminate", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"warranty_id": "warranty-001", "is_valid": False}

    status_response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": "order-002", "product_id": "headphones-001"},
        headers=HEADERS,
    )
    assert status_response.json()["is_valid"] is False


def test_terminate_for_unknown_warranty_id_returns_404(client):
    response = client.patch("/api/v1/warranty/does-not-exist/terminate", headers=HEADERS)
    assert response.status_code == 404
    assert "error" in response.json()


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
