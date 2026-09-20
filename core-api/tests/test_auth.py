"""Isolated tests for the X-API-Key dependency and the two principals it tells apart."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_api_key, require_operator_key
from app.errors import register_exception_handlers

app_under_test = FastAPI()
register_exception_handlers(app_under_test)


@app_under_test.get("/protected")
def protected(principal: str = Depends(require_api_key)) -> dict:
    return {"principal": principal}


@app_under_test.get("/operator", dependencies=[Depends(require_operator_key)])
def operator_only() -> dict:
    return {"ok": True}


client = TestClient(app_under_test)


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("TOOLS_API_KEY", "expected-key")
    monkeypatch.setenv("OPERATOR_API_KEY", "operator-key")


def test_missing_api_key_is_rejected():
    assert client.get("/protected").status_code == 401


def test_wrong_api_key_is_rejected():
    assert client.get("/protected", headers={"X-API-Key": "wrong-key"}).status_code == 401


def test_correct_api_key_is_accepted_as_the_agent():
    response = client.get("/protected", headers={"X-API-Key": "expected-key"})
    assert response.status_code == 200
    assert response.json() == {"principal": "agent"}


def test_the_operator_key_is_accepted_as_the_operator():
    response = client.get("/protected", headers={"X-API-Key": "operator-key"})
    assert response.status_code == 200
    assert response.json() == {"principal": "operator"}


def test_an_operator_endpoint_refuses_the_agent_key():
    response = client.get("/operator", headers={"X-API-Key": "expected-key"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "operator_only"


def test_an_operator_endpoint_accepts_the_operator_key():
    assert client.get("/operator", headers={"X-API-Key": "operator-key"}).status_code == 200


def test_two_keys_set_to_the_same_value_fail_loudly_instead_of_promoting_the_agent(monkeypatch):
    monkeypatch.setenv("OPERATOR_API_KEY", "expected-key")
    assert client.get("/protected", headers={"X-API-Key": "expected-key"}).json() == {
        "principal": "agent"
    }
    assert client.get("/operator", headers={"X-API-Key": "expected-key"}).status_code == 403
