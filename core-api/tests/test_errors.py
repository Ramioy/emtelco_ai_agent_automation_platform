"""Isolated tests for the uniform error envelope; the raising endpoints live only here."""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import DomainError, register_exception_handlers

app_under_test = FastAPI()
register_exception_handlers(app_under_test)


@app_under_test.get("/domain-error")
def raise_domain_error():
    raise DomainError(status_code=404, code="not_found", message="Resource not found")


@app_under_test.get("/http-error")
def raise_http_error():
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


class Payload(BaseModel):
    name: str


@app_under_test.post("/validated")
def raise_validation_error(payload: Payload):
    return {"name": payload.name}


client = TestClient(app_under_test)


def test_domain_error_uses_the_uniform_envelope():
    response = client.get("/domain-error")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Resource not found"}
    }


def test_http_exception_also_uses_the_uniform_envelope():
    response = client.get("/http-error")
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "401", "message": "Invalid or missing API key"}
    }


def test_payload_validation_error_lists_the_field_and_reason():
    response = client.post("/validated", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["errors"][0]["field"] == "name"
    assert "reason" in body["errors"][0]
