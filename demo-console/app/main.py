"""Operations console for the demo: read the store state and change it in one click."""
from datetime import datetime
from html import escape
from enum import Enum
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app import store_api, views

app = FastAPI(title="Demo Console", docs_url=None, redoc_url=None, openapi_url=None)

OrderStatus = Enum("OrderStatus", {status: status for status in views.ORDER_STATUSES}, type=str)
TicketStatus = Enum(
    "TicketStatus", {status: status for status in views.TICKET_STATUS_LABELS}, type=str
)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/", response_class=HTMLResponse)
def dashboard(
    order: str | None = None,
    warranty: str | None = None,
    ticket: str | None = None,
    problem: str | None = None,
) -> HTMLResponse:
    try:
        orders = store_api.list_orders()
        warranties = store_api.list_warranties()
        tickets = store_api.list_tickets()
        client_ids = {item["client_id"] for item in orders}
        client_ids.update(item["client_id"] for item in tickets if item.get("client_id"))
        names = store_api.client_names(sorted(client_ids))
    except httpx.HTTPError as exc:
        return _unreachable(exc)

    return HTMLResponse(
        views.render_dashboard(
            orders=orders,
            warranties=warranties,
            tickets=tickets,
            names=names,
            read_at=datetime.now().strftime("%H:%M:%S"),
            notice=_notice(order, orders, warranty, warranties, ticket, tickets),
            problem=problem,
            touched=order or warranty or ticket,
        )
    )


@app.post("/orders/{order_id}/status/{status}")
def change_order_status(order_id: str, status: OrderStatus):
    try:
        store_api.set_order_status(order_id, status.value)
    except httpx.HTTPError as exc:
        return _unreachable(exc)
    return _back(f"/?order={order_id}")


@app.post("/warranties/{warranty_id}/terminate")
def expire_warranty(warranty_id: str):
    try:
        store_api.terminate_warranty(warranty_id)
    except httpx.HTTPError as exc:
        return _unreachable(exc)
    return _back(f"/?warranty={warranty_id}")


@app.post("/warranties/{warranty_id}/reinstate")
def reinstate_warranty(warranty_id: str):
    try:
        store_api.reinstate_warranty(warranty_id)
    except httpx.HTTPError as exc:
        return _unreachable(exc)
    return _back(f"/?warranty={warranty_id}")


@app.post("/warranties/{warranty_id}/edit")
def edit_warranty(
    warranty_id: str,
    coverage_months: int = Form(...),
    purchase_date: str = Form(...),
):
    try:
        store_api.update_warranty(warranty_id, coverage_months, purchase_date)
    except httpx.HTTPError as exc:
        return _unreachable(exc)
    return _back(f"/?warranty={warranty_id}")


@app.post("/tickets/{ticket_id}/{status}")
def move_ticket(
    ticket_id: str,
    status: TicketStatus,
    assignee: str = Form(default=""),
    resolution_note: str = Form(default=""),
):
    """The microservice owns the lifecycle rules, so a refusal comes back as its own message
    rather than as a console error page: that refusal is the point of the safety case."""
    try:
        store_api.update_ticket(
            ticket_id, status.value, assignee.strip() or None, resolution_note.strip() or None
        )
    except httpx.HTTPStatusError as exc:
        return _back(f"/?ticket={ticket_id}&problem={quote(_refusal(exc))}")
    except httpx.HTTPError as exc:
        return _unreachable(exc)
    return _back(f"/?ticket={ticket_id}")


def _refusal(exc: httpx.HTTPStatusError) -> str:
    try:
        error = exc.response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return f"El microservicio respondio {exc.response.status_code}."
    return views.REFUSAL_MESSAGES.get(error.get("code"), error.get("message", ""))


def _back(url: str) -> RedirectResponse:
    """303 so the browser re-reads the state with a GET and a refresh never replays the change."""
    return RedirectResponse(url=url, status_code=303)


def _unreachable(exc: httpx.HTTPError) -> HTMLResponse:
    detail = f"El microservicio en {store_api.BASE_URL} no respondio como se esperaba: {exc}"
    return HTMLResponse(views.render_unreachable(detail), status_code=502)


def _notice(
    order_id: str | None,
    orders: list[dict],
    warranty_id: str | None,
    warranties: list[dict],
    ticket_id: str | None = None,
    tickets: list[dict] | None = None,
) -> str | None:
    """Built from the state just read back, so the banner reports what the store now says.
    The only markup it carries is its own <strong>; everything read from the store is escaped,
    because this string is the one place a banner is rendered raw."""
    if order_id:
        for order in orders:
            if order["order_id"] == order_id:
                return (
                    f"El pedido <strong>{escape(order['order_id'])}</strong> quedo en "
                    f"<strong>{escape(order['status'])}</strong>. Preguntale al agente otra vez."
                )
    if warranty_id:
        for warranty in warranties:
            if warranty["warranty_id"] == warranty_id:
                state = "vigente" if warranty["is_valid"] else "vencida"
                return (
                    f"La garantia <strong>{escape(warranty['warranty_id'])}</strong> quedo "
                    f"<strong>{state}</strong>. Preguntale al agente otra vez."
                )
    if ticket_id:
        for ticket in tickets or []:
            if ticket["ticket_id"] == ticket_id:
                label = views.TICKET_STATUS_LABELS.get(ticket["status"], ticket["status"])
                return (
                    f"El ticket <strong>{escape(ticket['ticket_id'])}</strong> quedo en "
                    f"<strong>{escape(label)}</strong>."
                )
    return None
