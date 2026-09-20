"""Tests for the cross-session client_memory repository."""
import pytest

from app.db import init_db
from app.repositories import client_memory as client_memory_repo
from app.repositories import clients as clients_repo
from app.schemas.clients import ClientCreate
from app.schemas.sessions import Session


@pytest.fixture
def connection(tmp_path):
    conn = init_db(tmp_path / "test.db")
    clients_repo.insert(
        conn,
        ClientCreate(
            client_id="1234567",
            full_name="Juan Perez",
            phone="3001234567",
            email="juan@example.com",
        ),
    )
    yield conn
    conn.close()


def test_get_returns_none_when_no_memory_exists(connection):
    assert client_memory_repo.get(connection, "1234567") is None


def test_upsert_from_new_session_creates_memory(connection):
    session = Session(
        session_id="session-a",
        client_id="1234567",
        client_name="Juan",
        mentioned_budgets=[5_000_000],
        products_viewed=["laptop-a"],
        preferences=["graphic design"],
    )
    client_memory_repo.upsert_from_session(connection, session)
    memory = client_memory_repo.get(connection, "1234567")
    assert memory.mentioned_budgets == [5_000_000]
    assert memory.products_viewed == ["laptop-a"]
    assert memory.preferences == ["graphic design"]
    assert memory.last_session_id == "session-a"


def test_upsert_from_second_session_accumulates_list_fields(connection):
    client_memory_repo.upsert_from_session(
        connection,
        Session(
            session_id="session-a",
            client_id="1234567",
            mentioned_budgets=[5_000_000],
            products_viewed=["laptop-a"],
        ),
    )
    memory = client_memory_repo.upsert_from_session(
        connection,
        Session(
            session_id="session-b",
            client_id="1234567",
            mentioned_budgets=[6_000_000],
            products_viewed=["laptop-b"],
        ),
    )
    assert memory.mentioned_budgets == [5_000_000, 6_000_000]
    assert memory.products_viewed == ["laptop-a", "laptop-b"]
    assert memory.last_session_id == "session-b"


def test_mentioned_budget_reappearing_moves_to_the_end(connection):
    client_memory_repo.upsert_from_session(
        connection,
        Session(session_id="session-a", client_id="1234567", mentioned_budgets=[5_000_000]),
    )
    client_memory_repo.upsert_from_session(
        connection,
        Session(session_id="session-a", client_id="1234567", mentioned_budgets=[6_000_000]),
    )
    memory = client_memory_repo.upsert_from_session(
        connection,
        Session(session_id="session-b", client_id="1234567", mentioned_budgets=[5_000_000]),
    )
    assert memory.mentioned_budgets == [5_000_000, 6_000_000, 5_000_000]


def test_upsert_requires_a_linked_session(connection):
    with pytest.raises(ValueError):
        client_memory_repo.upsert_from_session(connection, Session(session_id="session-a"))
