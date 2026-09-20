"""Tests for the sessions SQL repository, against a temporary SQLite database."""
import pytest

from app.db import init_db
from app.repositories import client_memory as client_memory_repo
from app.repositories import clients as clients_repo
from app.repositories import sessions as sessions_repo
from app.schemas.clients import ClientCreate
from app.schemas.sessions import SessionUpdate


@pytest.fixture
def connection(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def test_link_client_migrates_pre_identification_data_immediately(connection):
    clients_repo.insert(
        connection,
        ClientCreate(
            client_id="1234567",
            full_name="Juan Perez",
            phone="3001234567",
            email="juan@example.com",
        ),
    )
    sessions_repo.update(connection, "session-a", SessionUpdate(mentioned_budget=5_000_000))
    sessions_repo.update(connection, "session-a", SessionUpdate(product_viewed="laptop-a"))

    session = sessions_repo.link_client(connection, "session-a", "1234567")

    assert session.client_id == "1234567"
    memory = client_memory_repo.get(connection, "1234567")
    assert memory.mentioned_budgets == [5_000_000]
    assert memory.products_viewed == ["laptop-a"]


def test_link_client_and_update_both_leave_an_audit_trail(connection):
    clients_repo.insert(
        connection,
        ClientCreate(
            client_id="1234567",
            full_name="Juan Perez",
            phone="3001234567",
            email="juan@example.com",
        ),
    )
    sessions_repo.link_client(connection, "session-a", "1234567")
    sessions_repo.update(connection, "session-a", SessionUpdate(mentioned_budget=5_000_000))

    rows = connection.execute(
        "SELECT type FROM interactions WHERE session_id = 'session-a' ORDER BY id"
    ).fetchall()
    assert [row[0] for row in rows] == ["note", "budget"]


def test_update_after_linking_also_flows_into_client_memory(connection):
    clients_repo.insert(
        connection,
        ClientCreate(
            client_id="1234567",
            full_name="Juan Perez",
            phone="3001234567",
            email="juan@example.com",
        ),
    )
    sessions_repo.link_client(connection, "session-a", "1234567")
    sessions_repo.update(connection, "session-a", SessionUpdate(mentioned_budget=5_000_000))

    memory = client_memory_repo.get(connection, "1234567")
    assert memory.mentioned_budgets == [5_000_000]


def test_get_or_create_creates_a_row_on_first_access(connection):
    session = sessions_repo.get_or_create(connection, "session-1")
    assert session.session_id == "session-1"
    assert session.client_id is None
    assert session.mentioned_budgets == []


def test_get_or_create_returns_the_same_row_on_second_access(connection):
    sessions_repo.get_or_create(connection, "session-1")
    session = sessions_repo.get_or_create(connection, "session-1")
    assert session.session_id == "session-1"


def test_update_sets_scalar_fields_without_touching_others(connection):
    sessions_repo.update(connection, "session-1", SessionUpdate(client_name="Juan"))
    session = sessions_repo.update(
        connection, "session-1", SessionUpdate(last_order_checked="order-9")
    )
    assert session.client_name == "Juan"
    assert session.last_order_checked == "order-9"


def test_two_updates_accumulate_list_fields_without_overwriting(connection):
    sessions_repo.update(connection, "session-1", SessionUpdate(product_viewed="laptop-a"))
    session = sessions_repo.update(
        connection, "session-1", SessionUpdate(product_viewed="laptop-b")
    )
    assert session.products_viewed == ["laptop-a", "laptop-b"]


def test_preference_is_not_duplicated_if_repeated(connection):
    sessions_repo.update(connection, "session-1", SessionUpdate(preference="graphic design"))
    session = sessions_repo.update(
        connection, "session-1", SessionUpdate(preference="graphic design")
    )
    assert session.preferences == ["graphic design"]


def test_mentioned_budget_ignores_an_immediate_repeat(connection):
    sessions_repo.update(connection, "session-1", SessionUpdate(mentioned_budget=5_000_000))
    session = sessions_repo.update(
        connection, "session-1", SessionUpdate(mentioned_budget=5_000_000)
    )
    assert session.mentioned_budgets == [5_000_000]


def test_mentioned_budget_appends_a_new_value(connection):
    sessions_repo.update(connection, "session-1", SessionUpdate(mentioned_budget=5_000_000))
    session = sessions_repo.update(
        connection, "session-1", SessionUpdate(mentioned_budget=6_000_000)
    )
    assert session.mentioned_budgets == [5_000_000, 6_000_000]


def test_mentioned_budget_reappends_when_it_reappears_after_a_different_value(connection):
    sessions_repo.update(connection, "session-1", SessionUpdate(mentioned_budget=5_000_000))
    sessions_repo.update(connection, "session-1", SessionUpdate(mentioned_budget=6_000_000))
    session = sessions_repo.update(
        connection, "session-1", SessionUpdate(mentioned_budget=5_000_000)
    )
    assert session.mentioned_budgets == [5_000_000, 6_000_000, 5_000_000]


def test_record_products_viewed_appends_all_new_ids_in_one_call(connection):
    session = sessions_repo.record_products_viewed(
        connection, "session-1", ["laptop-a", "laptop-b"]
    )
    assert session.products_viewed == ["laptop-a", "laptop-b"]


def test_record_products_viewed_does_not_duplicate_already_seen_ids(connection):
    sessions_repo.record_products_viewed(connection, "session-1", ["laptop-a"])
    session = sessions_repo.record_products_viewed(
        connection, "session-1", ["laptop-a", "laptop-b"]
    )
    assert session.products_viewed == ["laptop-a", "laptop-b"]


def test_record_products_viewed_logs_one_interaction_per_new_id(connection):
    sessions_repo.record_products_viewed(connection, "session-1", ["laptop-a", "laptop-b"])
    rows = connection.execute(
        "SELECT type FROM interactions WHERE session_id = 'session-1' ORDER BY id"
    ).fetchall()
    assert [row[0] for row in rows] == ["note", "note"]


def test_record_products_viewed_flows_into_client_memory_when_already_linked(connection):
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
    sessions_repo.record_products_viewed(connection, "session-1", ["laptop-a"])

    memory = client_memory_repo.get(connection, "1234567")
    assert memory.products_viewed == ["laptop-a"]


def test_record_last_order_checked_sets_the_field(connection):
    session = sessions_repo.record_last_order_checked(connection, "session-1", "order-001")
    assert session.last_order_checked == "order-001"


def test_record_last_order_checked_overwrites_the_previous_value(connection):
    sessions_repo.record_last_order_checked(connection, "session-1", "order-001")
    session = sessions_repo.record_last_order_checked(connection, "session-1", "order-002")
    assert session.last_order_checked == "order-002"
