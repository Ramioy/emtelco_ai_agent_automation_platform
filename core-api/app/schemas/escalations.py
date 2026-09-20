"""Pydantic schemas for the escalations domain."""
from pydantic import BaseModel


class Escalation(BaseModel):
    ticket_id: str
    session_id: str | None
    client_id: str | None
    reason: str
    priority: str
    status: str
    created_at: str


class EscalationCreateRequest(BaseModel):
    session_id: str
    reason: str
    priority: str


class EscalationCreateResponse(BaseModel):
    ticket_id: str
    status: str
