"""Pydantic schemas for the warranty domain."""
from datetime import date

from pydantic import BaseModel, Field, field_validator

MAX_COVERAGE_MONTHS = 120


class Warranty(BaseModel):
    warranty_id: str
    order_id: str
    product_id: str
    coverage_months: int
    purchase_date: str


class WarrantyValidity(BaseModel):
    is_valid: bool
    months_remaining: int


class WarrantySummary(BaseModel):
    warranty_id: str
    order_id: str
    product_id: str
    product_name: str | None = None
    coverage_months: int
    purchase_date: str
    is_valid: bool
    months_remaining: int


class WarrantyUpdateRequest(BaseModel):
    """Both fields optional: an operator may correct only one of the two."""

    coverage_months: int | None = Field(default=None, ge=0, le=MAX_COVERAGE_MONTHS)
    purchase_date: str | None = None

    @field_validator("purchase_date")
    @classmethod
    def validate_purchase_date(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError("purchase_date must be an ISO date, for example 2026-01-31")


class WarrantyStateResponse(BaseModel):
    """Answer of both operator-only state changes, so terminate and reinstate read the same."""

    warranty_id: str
    is_valid: bool
    coverage_months: int
    purchase_date: str
    months_remaining: int
