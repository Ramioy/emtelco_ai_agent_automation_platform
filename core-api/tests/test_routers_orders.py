"""Integration tests for the orders router against the real FastAPI app."""
from datetime import date, timedelta

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


def test_get_status_returns_status_and_products(client):
    response = client.get("/api/v1/orders/order-002/status", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == "order-002"
    assert body["status"] == "DISPATCHED"
    assert body["products"] == ["headphones-001"]


def test_get_status_for_unknown_order_returns_404(client):
    response = client.get("/api/v1/orders/does-not-exist/status", headers=HEADERS)
    assert response.status_code == 404
    assert "error" in response.json()


def test_get_status_with_session_id_records_last_order_checked(client):
    response = client.get(
        "/api/v1/orders/order-002/status",
        params={"session_id": "session-x"},
        headers=HEADERS,
    )
    assert response.status_code == 200

    session = client.get("/api/v1/sessions/session-x", headers=HEADERS).json()
    assert session["last_order_checked"] == "order-002"


def test_get_status_with_session_id_overwrites_a_previous_last_order_checked(client):
    client.get(
        "/api/v1/orders/order-001/status", params={"session_id": "session-x"}, headers=HEADERS
    )
    client.get(
        "/api/v1/orders/order-002/status", params={"session_id": "session-x"}, headers=HEADERS
    )
    session = client.get("/api/v1/sessions/session-x", headers=HEADERS).json()
    assert session["last_order_checked"] == "order-002"


def test_get_status_without_session_id_does_not_touch_any_session(client):
    client.get("/api/v1/orders/order-002/status", headers=HEADERS)
    session = client.get("/api/v1/sessions/session-untouched", headers=HEADERS).json()
    assert session["last_order_checked"] is None


def test_get_eta_returns_estimated_delivery_date(client):
    response = client.get("/api/v1/orders/order-002/eta", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body == {"order_id": "order-002", "estimated_delivery_date": "2026-09-21"}


def test_get_eta_for_unknown_order_returns_404(client):
    response = client.get("/api/v1/orders/does-not-exist/eta", headers=HEADERS)
    assert response.status_code == 404


def test_get_orders_by_client_returns_only_that_clients_orders(client):
    response = client.get("/api/v1/orders/by-client/1010101010", headers=HEADERS)
    assert response.status_code == 200
    order_ids = {order["order_id"] for order in response.json()}
    assert order_ids == {"order-001", "order-002", "order-003", "order-004"}


def test_get_orders_by_client_for_unknown_client_returns_empty(client):
    response = client.get("/api/v1/orders/by-client/9999999999", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == []


def test_update_address_on_active_order_returns_200_with_new_address(client):
    response = client.patch(
        "/api/v1/orders/order-001/address",
        json={"delivery_address": "Nueva Calle 99 # 1-11, Bogota"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json() == {
        "order_id": "order-001",
        "delivery_address": "Nueva Calle 99 # 1-11, Bogota",
    }


def test_update_address_on_delivered_order_returns_409(client):
    response = client.patch(
        "/api/v1/orders/order-003/address",
        json={"delivery_address": "Nueva Calle 99 # 1-11, Bogota"},
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert "error" in response.json()


def test_update_address_on_cancelled_order_returns_409(client):
    response = client.patch(
        "/api/v1/orders/order-004/address",
        json={"delivery_address": "Nueva Calle 99 # 1-11, Bogota"},
        headers=HEADERS,
    )
    assert response.status_code == 409


def test_update_address_for_unknown_order_returns_404(client):
    response = client.patch(
        "/api/v1/orders/does-not-exist/address",
        json={"delivery_address": "Nueva Calle 99 # 1-11, Bogota"},
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_dev_update_status_advances_order_and_is_reflected_on_status_endpoint(client):
    response = client.patch(
        "/api/v1/orders/order-006/status", json={"status": "DELIVERED"}, headers=HEADERS
    )
    assert response.status_code == 200
    assert response.json() == {"order_id": "order-006", "status": "DELIVERED"}

    status_response = client.get("/api/v1/orders/order-006/status", headers=HEADERS)
    assert status_response.json()["status"] == "DELIVERED"


def test_dev_update_status_rejects_a_value_outside_the_fixed_vocabulary(client):
    response = client.patch(
        "/api/v1/orders/order-006/status", json={"status": "SHIPPED"}, headers=HEADERS
    )
    assert response.status_code == 422


def test_dev_update_status_for_unknown_order_returns_404(client):
    response = client.patch(
        "/api/v1/orders/does-not-exist/status", json={"status": "DELIVERED"}, headers=HEADERS
    )
    assert response.status_code == 404


def test_requires_api_key(client):
    response = client.get("/api/v1/orders/order-001/status")
    assert response.status_code == 401


def test_create_order_with_stock_returns_201_and_decrements_stock(client):
    products_before = client.get(
        "/api/v1/catalog/products", params={"category": "laptop"}, headers=HEADERS
    ).json()
    stock_before = next(p["stock"] for p in products_before if p["id"] == "laptop-001")

    response = client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert "order_id" in body

    products_after = client.get(
        "/api/v1/catalog/products", params={"category": "laptop"}, headers=HEADERS
    ).json()
    stock_after = next(p["stock"] for p in products_after if p["id"] == "laptop-001")
    assert stock_after == stock_before - 1


def test_create_order_estimated_delivery_date_is_five_days_from_today(client):
    response = client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    expected = (date.today() + timedelta(days=5)).isoformat()
    assert response.json()["estimated_delivery_date"] == expected


def test_create_order_with_zero_stock_returns_409(client):
    response = client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "headphones-002",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert "error" in response.json()


def test_create_order_for_unknown_client_returns_404(client):
    response = client.post(
        "/api/v1/orders",
        json={
            "client_id": "9999999999",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_create_order_for_unknown_product_returns_404(client):
    response = client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "does-not-exist",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    assert response.status_code == 404


def test_create_order_with_session_id_records_last_order_checked(client):
    response = client.post(
        "/api/v1/orders",
        params={"session_id": "session-x"},
        json={
            "client_id": "1010101010",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    order_id = response.json()["order_id"]

    session = client.get("/api/v1/sessions/session-x", headers=HEADERS).json()
    assert session["last_order_checked"] == order_id


def test_create_order_without_session_id_does_not_touch_any_session(client):
    client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    session = client.get("/api/v1/sessions/session-untouched", headers=HEADERS).json()
    assert session["last_order_checked"] is None
