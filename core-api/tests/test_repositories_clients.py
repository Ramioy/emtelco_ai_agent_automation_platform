"""Tests for the clients SQL repository, against a temporary SQLite database."""
import sqlite3

import pytest

from app.db import init_db
from app.repositories import clients as clients_repo
from app.schemas.clients import ClientCreate

SAMPLE = ClientCreate(
    client_id="1234567",
    full_name="Juan Perez",
    phone="3001234567",
    email="juan.perez@example.com",
)


@pytest.fixture
def connection(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def test_exists_is_false_for_unknown_client(connection):
    assert clients_repo.exists(connection, SAMPLE.client_id) is False


def test_insert_then_exists_and_get(connection):
    clients_repo.insert(connection, SAMPLE)
    assert clients_repo.exists(connection, SAMPLE.client_id) is True
    stored = clients_repo.get(connection, SAMPLE.client_id)
    assert stored.full_name == SAMPLE.full_name
    assert stored.phone == SAMPLE.phone
    assert stored.email == SAMPLE.email


def test_get_returns_none_for_unknown_client(connection):
    assert clients_repo.get(connection, "9999999") is None


def test_insert_duplicate_client_id_raises_integrity_error(connection):
    clients_repo.insert(connection, SAMPLE)
    with pytest.raises(sqlite3.IntegrityError):
        clients_repo.insert(connection, SAMPLE)


def test_init_db_seeds_demo_clients_from_fixture(connection):
    assert clients_repo.exists(connection, "1010101010") is True
    assert clients_repo.exists(connection, "2020202020") is True


def test_seed_is_idempotent(connection):
    before = connection.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    clients_repo.seed(connection)
    after = connection.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    assert before == after
