"""Pydantic schemas for the orders domain."""
from pydantic import BaseModel, field_validator

ORDER_STATUSES = {"PENDING", "PROCESSING", "DISPATCHED", "IN_TRANSIT", "DELIVERED", "CANCELLED"}


class OrderProduct(BaseModel):
    """Commercial identity of a product in an order, so the agent can name it instead of
    reading the id out loud. name/brand/price are null when the id left the catalog."""

    product_id: str
    name: str | None = None
    brand: str | None = None
    price: int | None = None


class Order(BaseModel):
    order_id: str
    client_id: str
    status: str
    estimated_delivery_date: str
    delivery_address: str
    products: list[str]
    product_details: list[OrderProduct] = []


class OrderStatusResponse(BaseModel):
    order_id: str
    status: str
    products: list[str]
    product_details: list[OrderProduct] = []


class OrderEtaResponse(BaseModel):
    order_id: str
    estimated_delivery_date: str
    product_details: list[OrderProduct] = []


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
    # Optional on purpose: with isolation on, the buyer comes from the trusted identity and a
    # value sent here may only agree with it. It is only required with isolation disabled.
    client_id: str | None = None
    product_id: str
    delivery_address: str


class OrderCreateResponse(BaseModel):
    order_id: str
    status: str
    estimated_delivery_date: str
    warranty_months: int
    product_details: list[OrderProduct] = []
