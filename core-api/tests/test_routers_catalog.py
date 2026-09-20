"""Integration tests for the catalog router against the real FastAPI app."""
import json

import pytest
from fastapi.testclient import TestClient

from app.db import get_db, init_db
from app.main import app
from app.repositories.catalog import SEED_PATH

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


def test_get_products_without_filters_returns_all(client):
    response = client.get("/api/v1/catalog/products", headers=HEADERS)
    assert response.status_code == 200
    seeded_ids = {product["id"] for product in json.loads(SEED_PATH.read_text())}
    assert {product["id"] for product in response.json()} == seeded_ids


def test_get_products_filters_by_category_and_max_budget(client):
    response = client.get(
        "/api/v1/catalog/products",
        params={"category": "laptop", "max_budget": 5000000},
        headers=HEADERS,
    )
    assert response.status_code == 200
    products = response.json()
    assert all(
        product["category"] == "laptop" and product["price"] <= 5000000 for product in products
    )
    ids = {product["id"] for product in products}
    assert {"laptop-001", "laptop-002"} <= ids
    assert "laptop-003" not in ids


def test_get_products_requires_api_key(client):
    response = client.get("/api/v1/catalog/products")
    assert response.status_code == 401


def test_get_products_with_session_id_records_results_in_products_viewed(client):
    response = client.get(
        "/api/v1/catalog/products",
        params={"category": "laptop", "session_id": "session-x"},
        headers=HEADERS,
    )
    assert response.status_code == 200
    queried_ids = {product["id"] for product in response.json()}
    assert {"laptop-001", "laptop-002", "laptop-003"} <= queried_ids

    session = client.get("/api/v1/sessions/session-x", headers=HEADERS).json()
    assert set(session["products_viewed"]) == queried_ids


def test_get_products_without_session_id_does_not_touch_any_session(client):
    client.get(
        "/api/v1/catalog/products",
        params={"category": "laptop"},
        headers=HEADERS,
    )
    session = client.get("/api/v1/sessions/session-untouched", headers=HEADERS).json()
    assert session["products_viewed"] == []


def test_get_products_with_session_id_does_not_duplicate_across_repeated_queries(client):
    first = client.get(
        "/api/v1/catalog/products",
        params={"category": "tablet", "session_id": "session-y"},
        headers=HEADERS,
    )
    client.get(
        "/api/v1/catalog/products",
        params={"category": "tablet", "session_id": "session-y"},
        headers=HEADERS,
    )
    queried_ids = [product["id"] for product in first.json()]
    session = client.get("/api/v1/sessions/session-y", headers=HEADERS).json()
    assert session["products_viewed"] == queried_ids


def test_get_products_with_session_id_and_no_matches_records_nothing(client):
    client.get(
        "/api/v1/catalog/products",
        params={"category": "drone", "session_id": "session-z"},
        headers=HEADERS,
    )
    session = client.get("/api/v1/sessions/session-z", headers=HEADERS).json()
    assert session["products_viewed"] == []


def test_compare_returns_computed_key_differences_over_two_real_ids(client):
    response = client.post(
        "/api/v1/catalog/compare",
        json={"ids": ["laptop-001", "smartphone-001"]},
        headers=HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert [product["id"] for product in body["products"]] == ["laptop-001", "smartphone-001"]

    differences = set(body["key_differences"])
    assert {"category", "brand", "price", "stock", "specs.storage_gb", "specs.screen_inches"} <= differences
    # ram_gb happens to be 8 for both fixtures: a genuinely computed diff excludes it.
    assert "specs.ram_gb" not in differences


def test_compare_with_unknown_id_returns_404(client):
    response = client.post(
        "/api/v1/catalog/compare",
        json={"ids": ["laptop-001", "does-not-exist"]},
        headers=HEADERS,
    )
    assert response.status_code == 404
    assert "error" in response.json()


def test_compare_with_fewer_than_two_ids_returns_422(client):
    response = client.post(
        "/api/v1/catalog/compare",
        json={"ids": ["laptop-001"]},
        headers=HEADERS,
    )
    assert response.status_code == 422


def test_every_product_on_sale_carries_a_coverage_term(client):
    products = client.get("/api/v1/catalog/products", headers=HEADERS).json()
    assert products
    assert all(product["warranty_months"] > 0 for product in products)
