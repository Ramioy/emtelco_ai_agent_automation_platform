"""HTTP endpoints for the warranty domain."""
import sqlite3
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app import identity
from app.auth import require_api_key, require_operator_key
from app.db import get_db
from app.errors import DomainError
from app.identity import Subject, get_subject
from app.repositories import catalog as catalog_repo
from app.repositories import escalations as escalations_repo
from app.repositories import orders as orders_repo
from app.repositories import warranty as warranty_repo
from app.repositories import warranty_claims as warranty_claims_repo
from app.schemas.warranty import (
    Warranty,
    WarrantyStateResponse,
    WarrantySummary,
    WarrantyUpdateRequest,
)
from app.schemas.escalations import SAFETY_RISK, WARRANTY_CLAIM
from app.schemas.warranty_claims import ClaimCreateRequest, ClaimCreateResponse

SAFETY_PRIORITY = "high"
CLAIM_PRIORITY = "medium"

router = APIRouter(
    prefix="/api/v1/warranty",
    tags=["warranty"],
    dependencies=[Depends(require_api_key)],
)


@router.get(
    "",
    response_model=list[WarrantySummary],
    dependencies=[Depends(require_operator_key)],
    summary="List every registered warranty (operations, not a tool)",
)
def list_warranties(connection: sqlite3.Connection = Depends(get_db)) -> list[WarrantySummary]:
    """Not exposed as an agent tool: the agent only ever asks about one order's coverage. It
    backs the operations console that drives the demo."""
    warranties = warranty_repo.list_all(connection)
    product_ids = [warranty.product_id for warranty in warranties]
    products = catalog_repo.get_by_ids(connection, product_ids) if product_ids else []
    names = {product.id: product.name for product in products}
    summaries = []
    for warranty in warranties:
        validity = warranty_repo.compute_validity(warranty)
        summaries.append(
            WarrantySummary(
                warranty_id=warranty.warranty_id,
                order_id=warranty.order_id,
                product_id=warranty.product_id,
                product_name=names.get(warranty.product_id),
                coverage_months=warranty.coverage_months,
                purchase_date=warranty.purchase_date,
                is_valid=validity.is_valid,
                months_remaining=validity.months_remaining,
            )
        )
    return summaries


@router.get("/status", summary="Check warranty status for an order/product")
def get_warranty_status(
    order_id: str,
    product_id: str,
    connection: sqlite3.Connection = Depends(get_db),
    subject: Subject = Depends(get_subject),
):
    """Distinguishes "no warranty registered at all" (404 {exists: false}, a functional
    branch the agent needs, same exception to the error envelope as GET /clients/{id}) from
    "had a warranty, but it already expired" (200 {is_valid: false, ...})."""
    warranty = warranty_repo.get(connection, order_id, product_id)
    if warranty is None:
        return JSONResponse(status_code=404, content={"exists": False})
    _authorize_order(connection, subject, warranty.order_id)
    return warranty_repo.compute_validity(warranty)


def _resolve_warranty_id(connection: sqlite3.Connection, order_id: str) -> str | None:
    """The claims request body only carries order_id, not product_id -- resolvable because
    an order always holds exactly one product. Returns None when the order carries no warranty:
    a claim on an uncovered product is still a claim, so this link is best-effort. The order
    itself has already been checked by the caller."""
    order = orders_repo.get(connection, order_id)
    if order is None or not order.products:
        return None
    warranty = warranty_repo.get(connection, order_id, order.products[0])
    return warranty.warranty_id if warranty is not None else None


@router.post(
    "/claims",
    response_model=ClaimCreateResponse,
    status_code=201,
    summary="File a warranty claim",
)
def create_warranty_claim(
    payload: ClaimCreateRequest,
    session_id: str | None = None,
    connection: sqlite3.Connection = Depends(get_db),
    subject: Subject = Depends(get_subject),
) -> ClaimCreateResponse:
    """Every claim is queued under the ticket number it returns, so that number stays readable."""
    _authorize_order(connection, subject, payload.order_id)
    client_id = identity.resolve_client_id(connection, subject, payload.client_id)
    escalated = warranty_claims_repo.matches_risk_keyword(payload.description)
    ticket_id = f"ticket-{uuid.uuid4().hex[:8]}"

    claim = warranty_claims_repo.create(
        connection,
        ticket_id=ticket_id,
        warranty_id=_resolve_warranty_id(connection, payload.order_id),
        client_id=client_id,
        description=payload.description,
        escalated=escalated,
    )

    if escalated:
        reason = f"Safety risk reported in a warranty claim: {payload.description}"
        origin, priority = SAFETY_RISK, SAFETY_PRIORITY
    else:
        reason = f"Warranty claim: {payload.description}"
        origin, priority = WARRANTY_CLAIM, CLAIM_PRIORITY

    escalations_repo.create(
        connection,
        ticket_id=ticket_id,
        session_id=session_id,
        client_id=client_id,
        reason=reason,
        priority=priority,
        origin=origin,
    )

    return ClaimCreateResponse(
        claim_id=claim.claim_id,
        ticket_id=claim.ticket_id,
        status="registered",
        escalated=claim.escalated,
    )


@router.patch(
    "/{warranty_id}/terminate",
    response_model=WarrantyStateResponse,
    dependencies=[Depends(require_operator_key)],
    summary="Force a warranty to expire (development only)",
)
def terminate_warranty_dev_only(
    warranty_id: str, connection: sqlite3.Connection = Depends(get_db)
) -> WarrantyStateResponse:
    """Development-only endpoint: not exposed as an agent tool, lets the demo video show an
    "expired warranty" case without waiting for a real one to lapse.
    Sets coverage to zero and reuses compute_validity's own formula, rather than a second
    is_valid flag that could drift out of sync with it. A record bought today is also
    backdated a day, because a window that closes today still counts as covered."""
    existing = warranty_repo.get_by_id(connection, warranty_id)
    if existing is None:
        raise _warranty_not_found(warranty_id)
    warranty = warranty_repo.update(
        connection,
        warranty_id,
        coverage_months=0,
        purchase_date=warranty_repo.purchase_date_for_termination(existing),
    )
    return _state_response(warranty)


@router.patch(
    "/{warranty_id}/reinstate",
    response_model=WarrantyStateResponse,
    dependencies=[Depends(require_operator_key)],
    summary="Put an expired warranty back under coverage (development only)",
)
def reinstate_warranty_dev_only(
    warranty_id: str, connection: sqlite3.Connection = Depends(get_db)
) -> WarrantyStateResponse:
    """The counterpart of terminate, so a demo can show the expired case and then come back
    from it. Two explicit endpoints rather than one toggle: each is idempotent, so a repeated
    click or a stale page cannot flip the warranty into the state nobody asked for.
    It does not put back the coverage the warranty had before: validity is purchase date plus
    coverage, so a warranty bought years ago would expire again the instant its original
    coverage returned. It extends coverage instead, leaving the same remaining window whatever
    the purchase date, and never rewrites that date, which belongs to the order."""
    existing = warranty_repo.get_by_id(connection, warranty_id)
    if existing is None:
        raise _warranty_not_found(warranty_id)
    coverage_months = warranty_repo.coverage_for_reinstatement(existing)
    warranty = warranty_repo.update_coverage_months(connection, warranty_id, coverage_months)
    return _state_response(warranty)


@router.patch(
    "/{warranty_id}",
    response_model=WarrantyStateResponse,
    dependencies=[Depends(require_operator_key)],
    summary="Edit a warranty's coverage or purchase date (development only)",
)
def update_warranty_dev_only(
    warranty_id: str,
    payload: WarrantyUpdateRequest,
    connection: sqlite3.Connection = Depends(get_db),
) -> WarrantyStateResponse:
    """The full editor behind the console, next to the two one-click shortcuts: coverage and
    purchase date are the only inputs validity is computed from, so between them an operator
    can stage any case the agent has to report, including ones neither shortcut produces."""
    if warranty_repo.get_by_id(connection, warranty_id) is None:
        raise _warranty_not_found(warranty_id)
    warranty = warranty_repo.update(
        connection,
        warranty_id,
        coverage_months=payload.coverage_months,
        purchase_date=payload.purchase_date,
    )
    return _state_response(warranty)


def _authorize_order(
    connection: sqlite3.Connection, subject: Subject, order_id: str
) -> None:
    """A warranty is reachable only through the order it was sold with, so the order's owner is
    what decides who may see it. A missing order is refused rather than waved through: with
    nobody to attribute the record to there is nobody it can be checked against."""
    order = orders_repo.get(connection, order_id)
    if order is None:
        raise DomainError(
            status_code=404, code="not_found", message=f"Order {order_id} not found"
        )
    identity.authorize_client_access(connection, subject, order.client_id)


def _warranty_not_found(warranty_id: str) -> DomainError:
    return DomainError(
        status_code=404, code="not_found", message=f"Warranty {warranty_id} not found"
    )


def _state_response(warranty: Warranty) -> WarrantyStateResponse:
    validity = warranty_repo.compute_validity(warranty)
    return WarrantyStateResponse(
        warranty_id=warranty.warranty_id,
        is_valid=validity.is_valid,
        coverage_months=warranty.coverage_months,
        purchase_date=warranty.purchase_date,
        months_remaining=validity.months_remaining,
    )
