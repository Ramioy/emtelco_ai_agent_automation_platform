"""Tests for the interactions audit log repository."""
import pytest

from app.db import init_db
from app.repositories import clients as clients_repo
from app.repositories import interactions as interactions_repo
from app.repositories import sessions as sessions_repo
from app.schemas.clients import ClientCreate


@pytest.fixture
def connection(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def test_log_inserts_a_row(connection):
    sessions_repo.get_or_create(connection, "session-1")
    interactions_repo.log(connection, "session-1", None, "note", {"field": "x", "value": "y"})
    row = connection.execute("SELECT session_id, type, detail FROM interactions").fetchone()
    assert row[0] == "session-1"
    assert row[1] == "note"
    assert row[2] == '{"field": "x", "value": "y"}'


def test_list_sessions_for_client_is_empty_when_none_linked(connection):
    assert interactions_repo.list_sessions_for_client(connection, "1234567") == []


def test_list_sessions_for_client_includes_a_summary_of_interaction_types(connection):
    clients_repo.insert(
        connection,
        ClientCreate(
            client_id="1234567",
            full_name="Juan Perez",
            phone="3001234567",
            email="juan@example.com",
        ),
    )
    sessions_repo.link_client(connection, "session-1", "1234567")
    interactions_repo.log(connection, "session-1", "1234567", "budget", {"value": 5_000_000})
    interactions_repo.log(connection, "session-1", "1234567", "preference", {"value": "design"})

    sessions = interactions_repo.list_sessions_for_client(connection, "1234567")
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "session-1"
    assert sessions[0]["summary"] == "budget, note, preference"
