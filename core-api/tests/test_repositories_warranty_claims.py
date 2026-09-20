"""Tests for the warranty claims SQL repository, against a temporary SQLite database."""
import sqlite3

import pytest

from app.db import init_db
from app.repositories import warranty_claims as warranty_claims_repo


@pytest.fixture
def connection(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def test_matches_risk_keyword_detects_each_listed_keyword():
    for keyword in ("humo", "fuego", "choque", "explot", "chispa"):
        assert warranty_claims_repo.matches_risk_keyword(f"el producto tiene {keyword}") is True


def test_matches_risk_keyword_is_case_insensitive():
    assert warranty_claims_repo.matches_risk_keyword("Sale HUMO del televisor") is True


def test_matches_risk_keyword_returns_false_for_a_neutral_description():
    assert warranty_claims_repo.matches_risk_keyword("el televisor no enciende") is False


def test_create_returns_the_claim_with_a_generated_claim_id(connection):
    claim = warranty_claims_repo.create(
        connection,
        ticket_id="ticket-1",
        warranty_id="warranty-001",
        client_id="1010101010",
        description="el televisor no enciende",
        escalated=False,
    )
    assert claim.claim_id.startswith("claim-")
    assert claim.ticket_id == "ticket-1"
    assert claim.warranty_id == "warranty-001"
    assert claim.client_id == "1010101010"
    assert claim.escalated is False


def test_create_stores_escalated_true_when_given(connection):
    claim = warranty_claims_repo.create(
        connection,
        ticket_id="ticket-2",
        warranty_id=None,
        client_id="1010101010",
        description="sale humo del televisor",
        escalated=True,
    )
    assert claim.escalated is True
    assert claim.warranty_id is None


def test_get_returns_none_for_unknown_claim_id(connection):
    assert warranty_claims_repo.get(connection, "does-not-exist") is None


def test_descriptions_by_ticket_id_maps_only_the_requested_tickets(connection):
    warranty_claims_repo.create(
        connection,
        ticket_id="ticket-a",
        warranty_id=None,
        client_id="1010101010",
        description="no enciende",
        escalated=False,
    )
    warranty_claims_repo.create(
        connection,
        ticket_id="ticket-b",
        warranty_id=None,
        client_id="1010101010",
        description="sale humo",
        escalated=True,
    )
    assert warranty_claims_repo.descriptions_by_ticket_id(
        connection, ["ticket-a", "ticket-missing"]
    ) == {"ticket-a": "no enciende"}


def test_descriptions_by_ticket_id_with_no_tickets_needs_no_query(connection):
    assert warranty_claims_repo.descriptions_by_ticket_id(connection, []) == {}


def test_two_claims_cannot_share_one_ticket_number(connection):
    warranty_claims_repo.create(
        connection,
        ticket_id="ticket-dup",
        warranty_id=None,
        client_id="1010101010",
        description="no enciende",
        escalated=False,
    )
    with pytest.raises(sqlite3.IntegrityError):
        warranty_claims_repo.create(
            connection,
            ticket_id="ticket-dup",
            warranty_id=None,
            client_id="1010101010",
            description="tampoco carga",
            escalated=False,
        )

