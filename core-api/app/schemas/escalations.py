"""Pydantic schemas and the ticket lifecycle for the escalations domain."""
from typing import Literal

from pydantic import BaseModel, field_validator

PENDING_AGENT = "pending_agent"
IN_PROGRESS = "in_progress"
RESOLVED = "resolved"

AGENT_REQUEST = "agent_request"
SAFETY_RISK = "safety_risk"

# Three states are all a believable queue needs: waiting, taken by a named person, closed with
# a note. Reopening exists so a resolved ticket can come back without a fourth state.
ALLOWED_TRANSITIONS = {
    PENDING_AGENT: (IN_PROGRESS, RESOLVED),
    IN_PROGRESS: (IN_PROGRESS, RESOLVED),
    RESOLVED: (IN_PROGRESS,),
}


class Escalation(BaseModel):
    ticket_id: str
    session_id: str | None
    client_id: str | None
    reason: str
    priority: str
    status: str
    created_at: str
    origin: str = AGENT_REQUEST
    assignee: str | None = None
    resolution_note: str | None = None
    updated_at: str | None = None


class EscalationCreateRequest(BaseModel):
    session_id: str
    reason: str
    priority: str


class EscalationCreateResponse(BaseModel):
    ticket_id: str
    status: str


class EscalationUpdateRequest(BaseModel):
    status: Literal["pending_agent", "in_progress", "resolved"]
    assignee: str | None = None
    resolution_note: str | None = None

    @field_validator("assignee", "resolution_note")
    @classmethod
    def blank_is_absent(cls, value: str | None) -> str | None:
        """Whitespace must not satisfy "a person took it" or "here is how it was resolved"."""
        return (value or "").strip() or None
