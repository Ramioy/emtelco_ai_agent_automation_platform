"""HTTP endpoints for the escalations domain: one agent tool, the rest operator-only."""
import sqlite3
import uuid

from fastapi import APIRouter, Depends

from app import identity
from app.auth import require_api_key, require_operator_key
from app.db import get_db
from app.errors import DomainError
from app.identity import Subject, get_subject
from app.repositories import escalations as escalations_repo
from app.repositories import sessions as sessions_repo
from app.schemas.escalations import (
    ALLOWED_TRANSITIONS,
    IN_PROGRESS,
    PENDING_AGENT,
    RESOLVED,
    SAFETY_RISK,
    Escalation,
    EscalationCreateRequest,
    EscalationCreateResponse,
    EscalationUpdateRequest,
)

router = APIRouter(prefix="/api/v1/escalations", tags=["escalations"])


@router.post(
    "",
    response_model=EscalationCreateResponse,
    status_code=201,
    dependencies=[Depends(require_api_key)],
    summary="Escalate a case to a human agent",
)
def create_escalation(
    payload: EscalationCreateRequest,
    connection: sqlite3.Connection = Depends(get_db),
    subject: Subject = Depends(get_subject),
) -> EscalationCreateResponse:
    """Reuses the same repository routine already exercised by the automatic warranty-claim
    escalation. The customer is taken from the trusted identity when there is one; asking for a
    human before identifying is still a legitimate request, so a ticket with no customer on it
    is allowed rather than refused."""
    session = sessions_repo.get_or_create(connection, payload.session_id)
    client_id = identity.bound_client_id(connection, subject)
    if client_id is None and not subject.enforced:
        client_id = session.client_id
    ticket_id = f"ticket-{uuid.uuid4().hex[:8]}"
    escalation = escalations_repo.create(
        connection,
        ticket_id=ticket_id,
        session_id=payload.session_id,
        client_id=client_id,
        reason=payload.reason,
        priority=payload.priority,
    )
    return EscalationCreateResponse(ticket_id=escalation.ticket_id, status=escalation.status)


@router.get(
    "",
    response_model=list[Escalation],
    dependencies=[Depends(require_operator_key)],
    summary="List every support ticket (operations, not a tool)",
)
def list_escalations(connection: sqlite3.Connection = Depends(get_db)) -> list[Escalation]:
    """Deliberately outside the agent's tool catalog: a customer-facing agent reading the whole
    ticket queue would hand one customer another customer's complaints."""
    return escalations_repo.list_all(connection)


@router.patch(
    "/{ticket_id}",
    response_model=Escalation,
    dependencies=[Depends(require_operator_key)],
    summary="Move a support ticket through its lifecycle (operations, not a tool)",
)
def update_escalation(
    ticket_id: str,
    payload: EscalationUpdateRequest,
    connection: sqlite3.Connection = Depends(get_db),
) -> Escalation:
    """The lifecycle is enforced here rather than in the console, so a ticket the store raised
    for a safety risk cannot be closed without a person having taken it, whatever the caller."""
    ticket = escalations_repo.get(connection, ticket_id)
    if ticket is None:
        raise DomainError(
            status_code=404, code="not_found", message=f"Ticket {ticket_id} not found"
        )

    if payload.status not in ALLOWED_TRANSITIONS.get(ticket.status, ()):
        raise DomainError(
            status_code=409,
            code="invalid_transition",
            message=f"A ticket in {ticket.status} cannot move to {payload.status}",
        )

    assignee = payload.assignee or ticket.assignee
    note = payload.resolution_note or ticket.resolution_note

    if payload.status == IN_PROGRESS and not assignee:
        raise DomainError(
            status_code=409,
            code="assignee_required",
            message="Taking a ticket needs the name of whoever is handling it",
        )
    if payload.status == RESOLVED:
        if ticket.origin == SAFETY_RISK and ticket.status == PENDING_AGENT:
            raise DomainError(
                status_code=409,
                code="human_review_required",
                message=(
                    "A safety-risk ticket has to be taken by a person before it can be closed"
                ),
            )
        if not note:
            raise DomainError(
                status_code=409,
                code="resolution_note_required",
                message="Closing a ticket needs a note saying how it was resolved",
            )

    return escalations_repo.update(
        connection,
        ticket_id,
        status=payload.status,
        assignee=payload.assignee,
        resolution_note=payload.resolution_note,
    )
