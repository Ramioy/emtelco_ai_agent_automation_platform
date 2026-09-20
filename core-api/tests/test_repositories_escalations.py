"""Tests for the escalations SQL repository, against a temporary SQLite database."""
import pytest

from app.db import init_db
from app.repositories import escalations as escalations_repo


@pytest.fixture
def connection(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def test_create_returns_a_pending_agent_escalation(connection):
    escalation = escalations_repo.create(
        connection,
        ticket_id="ticket-1",
        session_id="session-1",
        client_id="1010101010",
        reason="Customer requested to speak with a human",
        priority="high",
    )
    assert escalation.ticket_id == "ticket-1"
    assert escalation.session_id == "session-1"
    assert escalation.client_id == "1010101010"
    assert escalation.reason == "Customer requested to speak with a human"
    assert escalation.priority == "high"
    assert escalation.status == "pending_agent"


def test_create_allows_a_missing_session_id_and_client_id(connection):
    escalation = escalations_repo.create(
        connection,
        ticket_id="ticket-2",
        session_id=None,
        client_id=None,
        reason="Escalated without a known session or client",
        priority="high",
    )
    assert escalation.session_id is None
    assert escalation.client_id is None


def test_get_returns_none_for_unknown_ticket_id(connection):
    assert escalations_repo.get(connection, "does-not-exist") is None
