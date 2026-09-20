"""HTTP endpoints for the orders domain."""
import sqlite3
from datetime import date, timedelta

from fastapi import APIRouter, Depends

from app.auth import require_api_key
from app.db import get_db
from app.errors import DomainError
from app.repositories import catalog as catalog_repo
from app.repositories import clients as clients_repo
from app.repositories import orders as orders_repo
from app.repositories import sessions as sessions_repo
from app.schemas.orders import (
    AddressUpdateRequest,
    AddressUpdateResponse,
    Order,
    OrderCreateRequest,
    OrderCreateResponse,
    OrderEtaResponse,
    OrderStatusResponse,
    StatusUpdateRequest,
    StatusUpdateResponse,
)

DELIVERY_LEAD_TIME_DAYS = 5

NON_EDITABLE_STATUSES = {"DELIVERED", "CANCELLED"}

router = APIRouter(
    prefix="/api/v1/orders",
    tags=["orders"],
    dependencies=[Depends(require_api_key)],
)


def _get_or_404(connection: sqlite3.Connection, order_id: str) -> Order:
    order = orders_repo.get(connection, order_id)
    if order is None:
        raise DomainError(
            status_code=404, code="not_found", message=f"Order {order_id} not found"
        )
    return order


@router.post(
    "",
    response_model=OrderCreateResponse,
    status_code=201,
    summary="Create a simulated order for a single product",
)
def create_order(
    payload: OrderCreateRequest,
    session_id: str | None = None,
    connection: sqlite3.Connection = Depends(get_db),
) -> OrderCreateResponse:
    """Simulated order creation: one purchase = one product, no cart, no real payment.
    session_id is optional, same side effect as GET .../status (records the new order as
    this session's last_order_checked)."""
    if not clients_repo.exists(connection, payload.client_id):
        raise DomainError(
            status_code=404, code="not_found", message=f"Client {payload.client_id} not found"
        )

    products = catalog_repo.get_by_ids(connection, [payload.product_id])
    if not products:
        raise DomainError(
            status_code=404,
            code="not_found",
            message=f"Product {payload.product_id} not found",
        )
    product = products[0]
    if product.stock <= 0:
        raise DomainError(
            status_code=409,
            code="out_of_stock",
            message=f"Product {payload.product_id} has no stock available",
        )

    estimated_delivery_date = (date.today() + timedelta(days=DELIVERY_LEAD_TIME_DAYS)).isoformat()
    order = orders_repo.create(
        connection,
        client_id=payload.client_id,
        product_id=payload.product_id,
        delivery_address=payload.delivery_address,
        estimated_delivery_date=estimated_delivery_date,
    )
    catalog_repo.decrement_stock(connection, payload.product_id)

    if session_id is not None:
        sessions_repo.record_last_order_checked(connection, session_id, order.order_id)

    return OrderCreateResponse(
        order_id=order.order_id,
        status=order.status,
        estimated_delivery_date=order.estimated_delivery_date,
    )


@router.get(
    "/by-client/{client_id}", response_model=list[Order], summary="List all orders for a client"
)
def get_orders_by_client(
    client_id: str, connection: sqlite3.Connection = Depends(get_db)
) -> list[Order]:
    return orders_repo.list_by_client(connection, client_id)


@router.get(
    "/{order_id}/status",
    response_model=OrderStatusResponse,
    summary="Get an order's current status",
)
def get_order_status(
    order_id: str,
    session_id: str | None = None,
    connection: sqlite3.Connection = Depends(get_db),
) -> OrderStatusResponse:
    """session_id is optional: when given, this order id is recorded as that session's
    last_order_checked as a side effect."""
    order = _get_or_404(connection, order_id)
    if session_id is not None:
        sessions_repo.record_last_order_checked(connection, session_id, order.order_id)
    return OrderStatusResponse(
        order_id=order.order_id, status=order.status, products=order.products
    )


@router.get(
    "/{order_id}/eta",
    response_model=OrderEtaResponse,
    summary="Get an order's estimated delivery date",
)
def get_order_eta(
    order_id: str, connection: sqlite3.Connection = Depends(get_db)
) -> OrderEtaResponse:
    order = _get_or_404(connection, order_id)
    return OrderEtaResponse(
        order_id=order.order_id, estimated_delivery_date=order.estimated_delivery_date
    )


@router.patch(
    "/{order_id}/address",
    response_model=AddressUpdateResponse,
    summary="Update the delivery address of an active order",
)
def update_order_address(
    order_id: str,
    payload: AddressUpdateRequest,
    connection: sqlite3.Connection = Depends(get_db),
) -> AddressUpdateResponse:
    order = _get_or_404(connection, order_id)
    if order.status in NON_EDITABLE_STATUSES:
        raise DomainError(
            status_code=409,
            code="order_not_editable",
            message=f"Order {order_id} has status {order.status} and can no longer be edited",
        )
    updated = orders_repo.update_address(connection, order_id, payload.delivery_address)
    return AddressUpdateResponse(
        order_id=updated.order_id, delivery_address=updated.delivery_address
    )


@router.patch(
    "/{order_id}/status",
    response_model=StatusUpdateResponse,
    summary="Advance an order's status (development only)",
)
def update_order_status_dev_only(
    order_id: str,
    payload: StatusUpdateRequest,
    connection: sqlite3.Connection = Depends(get_db),
) -> StatusUpdateResponse:
    """Development-only endpoint: not exposed as an agent tool, lets the demo video advance
    a seeded order's status manually between takes."""
    _get_or_404(connection, order_id)
    updated = orders_repo.update_status(connection, order_id, payload.status)
    return StatusUpdateResponse(order_id=updated.order_id, status=updated.status)
