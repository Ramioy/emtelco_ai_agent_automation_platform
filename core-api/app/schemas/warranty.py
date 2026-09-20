"""Pydantic schemas for the warranty domain."""
from pydantic import BaseModel


class Warranty(BaseModel):
    warranty_id: str
    order_id: str
    product_id: str
    coverage_months: int
    purchase_date: str


class WarrantyValidity(BaseModel):
    is_valid: bool
    months_remaining: int


class TerminateResponse(BaseModel):
    warranty_id: str
    is_valid: bool
