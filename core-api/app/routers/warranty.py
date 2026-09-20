"""HTTP endpoints for the warranty domain."""
import sqlite3
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth import require_api_key
from app.db import get_db
from app.errors import DomainError
from app.repositories import escalations as escalations_repo
from app.repositories import orders as orders_repo
from app.repositories import warranty as warranty_repo
from app.repositories import warranty_claims as warranty_claims_repo
from app.schemas.warranty import TerminateResponse
from app.schemas.warranty_claims import ClaimCreateRequest, ClaimCreateResponse

ESCALATION_PRIORITY = "high"

router = APIRouter(
    prefix="/api/v1/warranty",
    tags=["warranty"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/status", summary="Check warranty status for an order/product")
def get_warranty_status(
    order_id: str, product_id: str, connection: sqlite3.Connection = Depends(get_db)
):
    """Distinguishes "no warranty registered at all" (404 {exists: false}, a functional
    branch the agent needs, same exception to the error envelope as GET /clients/{id}) from
    "had a warranty, but it already expired" (200 {is_valid: false, ...})."""
    warranty = warranty_repo.get(connection, order_id, product_id)
    if warranty is None:
        return JSONResponse(status_code=404, content={"exists": False})
    return warranty_repo.compute_validity(warranty)


def _resolve_warranty_id(connection: sqlite3.Connection, order_id: str) -> str | None:
    """The claims request body only carries order_id, not product_id -- resolvable because
    an order always holds exactly one product. Silently returns None (no error) if the order
    or its warranty isn't found: this is a best-effort audit link, not a validation gate."""
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
) -> ClaimCreateResponse:
    """escalated is computed from risk keywords in the description; when true, this endpoint
    also creates the escalations row itself -- defense in depth, so the safety case never
    depends on the agent remembering a second tool call."""
    escalated = warranty_claims_repo.matches_risk_keyword(payload.description)
    ticket_id = f"ticket-{uuid.uuid4().hex[:8]}"

    claim = warranty_claims_repo.create(
        connection,
        ticket_id=ticket_id,
        warranty_id=_resolve_warranty_id(connection, payload.order_id),
        client_id=payload.client_id,
        description=payload.description,
        escalated=escalated,
    )

    if escalated:
        reason = f"Risky warranty claim description: {payload.description!r}"
        escalations_repo.create(
            connection,
            ticket_id=ticket_id,
            session_id=session_id,
            client_id=payload.client_id,
            reason=reason,
            priority=ESCALATION_PRIORITY,
        )

    return ClaimCreateResponse(
        claim_id=claim.claim_id,
        ticket_id=claim.ticket_id,
        status="registered",
        escalated=claim.escalated,
    )


@router.patch(
    "/{warranty_id}/terminate",
    response_model=TerminateResponse,
    summary="Force a warranty to expire (development only)",
)
def terminate_warranty_dev_only(
    warranty_id: str, connection: sqlite3.Connection = Depends(get_db)
) -> TerminateResponse:
    """Development-only endpoint: not exposed as an agent tool, lets the demo video show an
    "expired warranty" case without waiting for a real one to lapse.
    Sets coverage_months=0 and reuses compute_validity's own formula, rather than a second
    is_valid flag that could drift out of sync with it."""
    warranty = warranty_repo.update_coverage_months(connection, warranty_id, 0)
    if warranty is None:
        raise DomainError(
            status_code=404, code="not_found", message=f"Warranty {warranty_id} not found"
        )
    validity = warranty_repo.compute_validity(warranty)
    return TerminateResponse(warranty_id=warranty.warranty_id, is_valid=validity.is_valid)
