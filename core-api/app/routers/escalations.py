"""HTTP endpoints for the escalations domain."""
import sqlite3
import uuid

from fastapi import APIRouter, Depends

from app.auth import require_api_key
from app.db import get_db
from app.repositories import escalations as escalations_repo
from app.repositories import sessions as sessions_repo
from app.schemas.escalations import EscalationCreateRequest, EscalationCreateResponse

router = APIRouter(
    prefix="/api/v1/escalations",
    tags=["escalations"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "",
    response_model=EscalationCreateResponse,
    status_code=201,
    summary="Escalate a case to a human agent",
)
def create_escalation(
    payload: EscalationCreateRequest,
    connection: sqlite3.Connection = Depends(get_db),
) -> EscalationCreateResponse:
    """Reuses the same repository routine already exercised by the automatic warranty-claim
    escalation. client_id isn't part of this request body, but is filled in from the session
    when it's already identified, rather than always left null."""
    session = sessions_repo.get_or_create(connection, payload.session_id)
    ticket_id = f"ticket-{uuid.uuid4().hex[:8]}"
    escalation = escalations_repo.create(
        connection,
        ticket_id=ticket_id,
        session_id=payload.session_id,
        client_id=session.client_id,
        reason=payload.reason,
        priority=payload.priority,
    )
    return EscalationCreateResponse(ticket_id=escalation.ticket_id, status=escalation.status)
