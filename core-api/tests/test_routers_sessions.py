"""Integration tests for the sessions router against the real FastAPI app."""
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


def test_get_creates_session_if_it_does_not_exist(client):
    response = client.get("/api/v1/sessions/session-1", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["session_id"] == "session-1"


def test_put_then_get_reflects_the_update(client):
    client.put(
        "/api/v1/sessions/session-1",
        json={"client_name": "Juan"},
        headers=HEADERS,
    )
    response = client.get("/api/v1/sessions/session-1", headers=HEADERS)
    assert response.json()["client_name"] == "Juan"


def test_two_puts_accumulate_list_fields_instead_of_overwriting(client):
    client.put(
        "/api/v1/sessions/session-1",
        json={"product_viewed": "laptop-a"},
        headers=HEADERS,
    )
    response = client.put(
        "/api/v1/sessions/session-1",
        json={"product_viewed": "laptop-b"},
        headers=HEADERS,
    )
    assert response.json()["products_viewed"] == ["laptop-a", "laptop-b"]


def test_request_without_api_key_is_rejected(client):
    response = client.get("/api/v1/sessions/session-1")
    assert response.status_code == 401
