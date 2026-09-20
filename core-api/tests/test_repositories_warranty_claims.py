"""Tests for the warranty claims SQL repository, against a temporary SQLite database."""
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
