"""Pydantic schemas for the catalog domain."""
from pydantic import BaseModel, Field


class Product(BaseModel):
    id: str
    category: str
    name: str
    brand: str
    price: int
    specs: dict
    stock: int
    warranty_months: int


class CompareRequest(BaseModel):
    ids: list[str] = Field(min_length=2)


class CompareResponse(BaseModel):
    products: list[Product]
    key_differences: list[str]
