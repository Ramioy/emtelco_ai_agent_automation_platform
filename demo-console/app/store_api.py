"""Server-side client for the microservice; the operator key stays in this process."""
import os

import httpx

BASE_URL = os.environ.get("CORE_API_BASE_URL", "http://api:8000").rstrip("/")
# The operator key, not the agent's. It is what reaches the list endpoints, and what keeps the
# console outside the per-customer isolation rule that binds a chat user to one customer.
API_KEY = os.environ.get("OPERATOR_API_KEY", "")
TIMEOUT = 10.0

_client = httpx.Client(base_url=BASE_URL, headers={"X-API-Key": API_KEY}, timeout=TIMEOUT)


def list_orders() -> list[dict]:
    response = _client.get("/api/v1/orders")
    response.raise_for_status()
    return response.json()


def list_warranties() -> list[dict]:
    response = _client.get("/api/v1/warranty")
    response.raise_for_status()
    return response.json()


def client_names(client_ids: list[str]) -> dict[str, str]:
    """One lookup per distinct client, so the tables can show a person instead of a number."""
    names = {}
    for client_id in client_ids:
        response = _client.get(f"/api/v1/clients/{client_id}")
        if response.status_code == 200:
            names[client_id] = response.json()["client"]["full_name"]
    return names


def set_order_status(order_id: str, status: str) -> dict:
    response = _client.patch(f"/api/v1/orders/{order_id}/status", json={"status": status})
    response.raise_for_status()
    return response.json()


def terminate_warranty(warranty_id: str) -> dict:
    response = _client.patch(f"/api/v1/warranty/{warranty_id}/terminate")
    response.raise_for_status()
    return response.json()


def reinstate_warranty(warranty_id: str) -> dict:
    response = _client.patch(f"/api/v1/warranty/{warranty_id}/reinstate")
    response.raise_for_status()
    return response.json()


def update_warranty(warranty_id: str, coverage_months: int, purchase_date: str) -> dict:
    response = _client.patch(
        f"/api/v1/warranty/{warranty_id}",
        json={"coverage_months": coverage_months, "purchase_date": purchase_date},
    )
    response.raise_for_status()
    return response.json()


def list_tickets() -> list[dict]:
    response = _client.get("/api/v1/escalations")
    response.raise_for_status()
    return response.json()


def update_ticket(
    ticket_id: str, status: str, assignee: str | None, resolution_note: str | None
) -> dict:
    payload = {"status": status}
    if assignee:
        payload["assignee"] = assignee
    if resolution_note:
        payload["resolution_note"] = resolution_note
    response = _client.patch(f"/api/v1/escalations/{ticket_id}", json=payload)
    response.raise_for_status()
    return response.json()
