"""Pydantic schemas for the orders domain."""
from pydantic import BaseModel, field_validator

ORDER_STATUSES = {"PENDING", "PROCESSING", "DISPATCHED", "IN_TRANSIT", "DELIVERED", "CANCELLED"}


class Order(BaseModel):
    order_id: str
    client_id: str
    status: str
    estimated_delivery_date: str
    delivery_address: str
    products: list[str]


class OrderStatusResponse(BaseModel):
    order_id: str
    status: str
    products: list[str]


class OrderEtaResponse(BaseModel):
    order_id: str
    estimated_delivery_date: str


class AddressUpdateRequest(BaseModel):
    delivery_address: str


class AddressUpdateResponse(BaseModel):
    order_id: str
    delivery_address: str


class StatusUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ORDER_STATUSES:
            raise ValueError(f"status must be one of {sorted(ORDER_STATUSES)}")
        return value


class StatusUpdateResponse(BaseModel):
    order_id: str
    status: str


class OrderCreateRequest(BaseModel):
    client_id: str
    product_id: str
    delivery_address: str


class OrderCreateResponse(BaseModel):
    order_id: str
    status: str
    estimated_delivery_date: str
