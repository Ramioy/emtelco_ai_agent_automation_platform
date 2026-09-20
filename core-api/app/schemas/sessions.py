"""Pydantic schemas for the sessions domain."""
from pydantic import BaseModel


class SessionUpdate(BaseModel):
    client_name: str | None = None
    mentioned_budget: int | None = None
    last_order_checked: str | None = None
    product_viewed: str | None = None
    preference: str | None = None


class Session(BaseModel):
    session_id: str
    client_id: str | None = None
    client_name: str | None = None
    mentioned_budgets: list[int] = []
    last_order_checked: str | None = None
    products_viewed: list[str] = []
    preferences: list[str] = []
