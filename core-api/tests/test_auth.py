"""Isolated tests for the X-API-Key dependency; not wired to the real app yet."""
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import require_api_key

app_under_test = FastAPI()


@app_under_test.get("/protected", dependencies=[Depends(require_api_key)])
def protected() -> dict:
    return {"ok": True}


client = TestClient(app_under_test)


def test_missing_api_key_is_rejected(monkeypatch):
    monkeypatch.setenv("TOOLS_API_KEY", "expected-key")
    response = client.get("/protected")
    assert response.status_code == 401


def test_wrong_api_key_is_rejected(monkeypatch):
    monkeypatch.setenv("TOOLS_API_KEY", "expected-key")
    response = client.get("/protected", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401


def test_correct_api_key_is_accepted(monkeypatch):
    monkeypatch.setenv("TOOLS_API_KEY", "expected-key")
    response = client.get("/protected", headers={"X-API-Key": "expected-key"})
    assert response.status_code == 200
