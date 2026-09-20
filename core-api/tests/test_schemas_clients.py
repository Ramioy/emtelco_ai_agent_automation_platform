"""Unit tests for client field validators; no database involved."""
import pytest
from pydantic import ValidationError

from app.schemas.clients import ClientCreate

VALID = {
    "client_id": "1234567",
    "full_name": "Juan Perez",
    "phone": "3001234567",
    "email": "juan.perez@example.com",
}


def make_client(**overrides) -> ClientCreate:
    return ClientCreate(**{**VALID, **overrides})


@pytest.mark.parametrize("value", ["1234", "12345678901", "7654321"])
def test_client_id_accepts_4_to_11_digits(value):
    assert make_client(client_id=value).client_id == value


@pytest.mark.parametrize("value", ["123", "123456789012", "12a4", ""])
def test_client_id_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        make_client(client_id=value)


@pytest.mark.parametrize("value", ["Juan Perez", "Ñoño Munoz", "A", "Maria Jose Nunez"])
def test_full_name_accepts_letters_spaces_and_enye(value):
    assert make_client(full_name=value).full_name == value


@pytest.mark.parametrize("value", ["Juan123", "Juan_Perez", "", "A" * 101])
def test_full_name_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        make_client(full_name=value)


@pytest.mark.parametrize("value", ["3001234567", "6009876543"])
def test_phone_accepts_10_digits_starting_with_3_or_6(value):
    assert make_client(phone=value).phone == value


@pytest.mark.parametrize("value", ["2001234567", "300123456", "30012345678", "300123456a"])
def test_phone_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        make_client(phone=value)


@pytest.mark.parametrize("value", ["juan@example.com", "a.b@sub.example.co"])
def test_email_accepts_valid_addresses(value):
    assert make_client(email=value).email == value


@pytest.mark.parametrize("value", ["juanexample.com", "juan@example", "juan @example.com"])
def test_email_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        make_client(email=value)
