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


def test_create_defaults_to_the_agent_request_origin(connection):
    escalation = escalations_repo.create(
        connection,
        ticket_id="ticket-3",
        session_id="session-1",
        client_id=None,
        reason="Customer asked for a person",
        priority="medium",
    )
    assert escalation.origin == "agent_request"
    assert escalation.assignee is None
    assert escalation.resolution_note is None
    assert escalation.updated_at is None


def test_create_records_the_safety_origin_when_given_one(connection):
    escalation = escalations_repo.create(
        connection,
        ticket_id="ticket-4",
        session_id=None,
        client_id="1010101010",
        reason="Risky warranty claim description",
        priority="high",
        origin="safety_risk",
    )
    assert escalation.origin == "safety_risk"


def test_list_all_returns_every_ticket_newest_first(connection):
    for index in (1, 2, 3):
        escalations_repo.create(
            connection,
            ticket_id=f"ticket-{index}",
            session_id=None,
            client_id=None,
            reason="reason",
            priority="low",
        )
    tickets = escalations_repo.list_all(connection)
    assert [ticket.ticket_id for ticket in tickets] == ["ticket-3", "ticket-2", "ticket-1"]


def test_update_sets_status_assignee_note_and_stamps_updated_at(connection):
    escalations_repo.create(
        connection,
        ticket_id="ticket-5",
        session_id=None,
        client_id=None,
        reason="reason",
        priority="low",
    )
    updated = escalations_repo.update(
        connection, "ticket-5", status="resolved", assignee="Laura", resolution_note="Listo"
    )
    assert updated.status == "resolved"
    assert updated.assignee == "Laura"
    assert updated.resolution_note == "Listo"
    assert updated.updated_at is not None


def test_update_leaves_a_stored_assignee_alone_when_none_is_sent(connection):
    escalations_repo.create(
        connection,
        ticket_id="ticket-6",
        session_id=None,
        client_id=None,
        reason="reason",
        priority="low",
    )
    escalations_repo.update(
        connection, "ticket-6", status="in_progress", assignee="Laura", resolution_note=None
    )
    updated = escalations_repo.update(
        connection, "ticket-6", status="resolved", assignee=None, resolution_note="Listo"
    )
    assert updated.assignee == "Laura"
