"""Pydantic schemas for the warranty claims domain."""
from pydantic import BaseModel


class WarrantyClaim(BaseModel):
    claim_id: str
    warranty_id: str | None
    client_id: str
    description: str
    ticket_id: str
    escalated: bool
    created_at: str


class ClaimCreateRequest(BaseModel):
    order_id: str
    description: str
    # Same rule as OrderCreateRequest: derived from the trusted identity when isolation is on.
    client_id: str | None = None


class ClaimCreateResponse(BaseModel):
    claim_id: str
    ticket_id: str
    status: str
    escalated: bool
