"""Pydantic schema for cross-session client memory."""
from pydantic import BaseModel


class ClientMemory(BaseModel):
    client_id: str
    client_name: str | None = None
    mentioned_budgets: list[int] = []
    last_order_checked: str | None = None
    products_viewed: list[str] = []
    preferences: list[str] = []
    last_session_id: str | None = None
