"""Integration tests for the orders router against the real FastAPI app."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import app

API_KEY = "test-key"
OPERATOR_KEY = "test-operator-key"
# The fixture identifies this end user as the seeded client who owns order-001..004, the way
# the agent does through verify_client before anything else.
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
    assert body["order_id"] == "order-002"
    assert body["estimated_delivery_date"] == "2026-09-21"


def test_get_eta_for_unknown_order_returns_404(client):
    response = client.get("/api/v1/orders/does-not-exist/eta", headers=HEADERS)
    assert response.status_code == 404


def test_get_orders_by_client_returns_only_that_clients_orders(client):
    response = client.get("/api/v1/orders/by-client/1010101010", headers=OPERATOR_HEADERS)
    assert response.status_code == 200
    order_ids = {order["order_id"] for order in response.json()}
    assert order_ids == {"order-001", "order-002", "order-003", "order-004"}


def test_get_orders_by_client_for_unknown_client_returns_empty(client):
    response = client.get("/api/v1/orders/by-client/9999999999", headers=OPERATOR_HEADERS)
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
        "/api/v1/orders/order-006/status", json={"status": "DELIVERED"}, headers=OPERATOR_HEADERS
    )
    assert response.status_code == 200
    assert response.json() == {"order_id": "order-006", "status": "DELIVERED"}

    status_response = client.get("/api/v1/orders/order-006/status", headers=OPERATOR_HEADERS)
    assert status_response.json()["status"] == "DELIVERED"


def test_dev_update_status_rejects_a_value_outside_the_fixed_vocabulary(client):
    response = client.patch(
        "/api/v1/orders/order-006/status", json={"status": "SHIPPED"}, headers=OPERATOR_HEADERS
    )
    assert response.status_code == 422


def test_dev_update_status_for_unknown_order_returns_404(client):
    response = client.patch(
        "/api/v1/orders/does-not-exist/status", json={"status": "DELIVERED"}, headers=OPERATOR_HEADERS
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
    """Reached through the operator key: an isolated end user has no way to name a client at
    all, so the branch only exists for a caller whose client_id is not derived."""
    response = client.post(
        "/api/v1/orders",
        json={
            "client_id": "9999999999",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=OPERATOR_HEADERS,
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


def test_get_status_names_the_product_instead_of_only_its_id(client):
    response = client.get("/api/v1/orders/order-002/status", headers=HEADERS)
    assert response.json()["product_details"] == [
        {
            "product_id": "headphones-001",
            "name": "SoundWave ANC",
            "brand": "Aurex",
            "price": 650000,
        }
    ]


def test_get_status_for_a_product_off_the_catalog_still_lists_it_with_null_fields(
    client, db_connection
):
    db_connection.execute("DELETE FROM products WHERE id = ?", ("headphones-001",))
    response = client.get("/api/v1/orders/order-002/status", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["products"] == ["headphones-001"]
    assert body["product_details"] == [
        {"product_id": "headphones-001", "name": None, "brand": None, "price": None}
    ]


def test_get_eta_carries_product_details(client):
    response = client.get("/api/v1/orders/order-002/eta", headers=HEADERS)
    assert response.json()["product_details"][0]["name"] == "SoundWave ANC"


def test_get_orders_by_client_carries_product_details(client):
    response = client.get("/api/v1/orders/by-client/2020202020", headers=OPERATOR_HEADERS)
    names = {order["order_id"]: order["product_details"][0]["name"] for order in response.json()}
    assert names == {"order-005": "Nova X12", "order-006": "UltraBook Air 14"}


def test_create_order_response_carries_product_details(client):
    response = client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    assert response.json()["product_details"] == [
        {
            "product_id": "laptop-001",
            "name": "UltraBook Air 14",
            "brand": "Zenda",
            "price": 3200000,
        }
    ]


def test_list_orders_returns_every_seeded_order(client):
    response = client.get("/api/v1/orders", headers=OPERATOR_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert [order["order_id"] for order in body] == [
        "order-001",
        "order-002",
        "order-003",
        "order-004",
        "order-005",
        "order-006",
    ]
    assert body[0]["client_id"] == "1010101010"
    assert body[0]["delivery_address"] == "Calle 10 # 5-20, Bogota"
    assert body[0]["product_details"][0]["name"] == "CreatorBook Pro 15"


def test_list_orders_reflects_a_status_change(client):
    client.patch(
        "/api/v1/orders/order-001/status",
        json={"status": "IN_TRANSIT"},
        headers=OPERATOR_HEADERS,
    )
    body = client.get("/api/v1/orders", headers=OPERATOR_HEADERS).json()
    assert next(o["status"] for o in body if o["order_id"] == "order-001") == "IN_TRANSIT"


def test_list_orders_requires_api_key(client):
    assert client.get("/api/v1/orders").status_code == 401


def test_create_order_issues_a_warranty_the_agent_can_check_right_away(client):
    order_id = client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    ).json()["order_id"]

    response = client.get(
        "/api/v1/warranty/status",
        params={"order_id": order_id, "product_id": "laptop-001"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["is_valid"] is True


def test_create_order_issues_the_coverage_the_product_is_sold_with(client):
    product = next(
        item
        for item in client.get("/api/v1/catalog/products", headers=HEADERS).json()
        if item["id"] == "laptop-001"
    )
    response = client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "laptop-001",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    assert response.json()["warranty_months"] == product["warranty_months"]

    warranties = client.get("/api/v1/warranty", headers=OPERATOR_HEADERS).json()
    issued = next(
        item for item in warranties if item["order_id"] == response.json()["order_id"]
    )
    assert issued["coverage_months"] == product["warranty_months"]
    assert issued["purchase_date"] == date.today().isoformat()
    assert issued["is_valid"] is True


def test_create_order_does_not_issue_a_warranty_when_it_is_refused(client):
    warranties_before = len(client.get("/api/v1/warranty", headers=HEADERS).json())
    client.post(
        "/api/v1/orders",
        json={
            "client_id": "1010101010",
            "product_id": "headphones-002",
            "delivery_address": "Calle Nueva 1",
        },
        headers=HEADERS,
    )
    assert len(client.get("/api/v1/warranty", headers=HEADERS).json()) == warranties_before
