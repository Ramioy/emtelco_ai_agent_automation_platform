"""Pydantic schemas and field validators for the clients domain."""
import re

from pydantic import BaseModel, field_validator

CLIENT_ID_PATTERN = re.compile(r"^\d{4,11}$")
FULL_NAME_PATTERN = re.compile(r"^[A-Za-zÁÉÍÓÚÑáéíóúñ ]{1,100}$")
PHONE_PATTERN = re.compile(r"^[36]\d{9}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ClientCreate(BaseModel):
    client_id: str
    full_name: str
    phone: str
    email: str

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, value: str) -> str:
        if not CLIENT_ID_PATTERN.match(value):
            raise ValueError("client_id must be 4 to 11 digits")
        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        if not FULL_NAME_PATTERN.match(value):
            raise ValueError(
                "full_name must be 1 to 100 characters, letters, spaces, "
                "accents, and enye only"
            )
        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        if not PHONE_PATTERN.match(value):
            raise ValueError("phone must be exactly 10 digits starting with 3 or 6")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not EMAIL_PATTERN.match(value):
            raise ValueError("email must be a valid address containing @")
        return value


class Client(BaseModel):
    client_id: str
    full_name: str
    phone: str
    email: str
