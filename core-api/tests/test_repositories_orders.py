"""Tests for the orders SQL repository, against a temporary SQLite database."""
import pytest

from app.db import init_db
from app.repositories import orders as orders_repo

ALL_STATUSES = {"PENDING", "PROCESSING", "DISPATCHED", "IN_TRANSIT", "DELIVERED", "CANCELLED"}


@pytest.fixture
def connection(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def test_init_db_seeds_orders_from_fixture(connection):
    count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    assert count > 0


def test_seed_is_idempotent(connection):
    before = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    orders_repo.seed(connection)
    after = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    assert before == after


def test_seed_covers_every_order_status(connection):
    rows = connection.execute("SELECT DISTINCT status FROM orders").fetchall()
    assert {row[0] for row in rows} == ALL_STATUSES


def test_get_returns_status_for_a_known_order(connection):
    order = orders_repo.get(connection, "order-002")
    assert order.status == "DISPATCHED"


def test_get_returns_estimated_delivery_date_for_eta(connection):
    order = orders_repo.get(connection, "order-002")
    assert order.estimated_delivery_date == "2026-09-21"


def test_get_returns_none_for_unknown_order(connection):
    assert orders_repo.get(connection, "does-not-exist") is None


def test_get_returns_parsed_products_and_fields(connection):
    order = orders_repo.get(connection, "order-001")
    assert order.client_id == "1010101010"
    assert order.delivery_address == "Calle 10 # 5-20, Bogota"
    assert order.products == ["laptop-002"]


def test_list_by_client_returns_only_that_clients_orders(connection):
    orders = orders_repo.list_by_client(connection, "1010101010")
    assert {order.order_id for order in orders} == {
        "order-001",
        "order-002",
        "order-003",
        "order-004",
    }


def test_list_by_client_for_a_different_client_returns_its_own_orders(connection):
    orders = orders_repo.list_by_client(connection, "2020202020")
    assert {order.order_id for order in orders} == {"order-005", "order-006"}


def test_list_by_client_for_unknown_client_returns_empty(connection):
    assert orders_repo.list_by_client(connection, "9999999999") == []


def test_update_address_changes_delivery_address_only(connection):
    updated = orders_repo.update_address(connection, "order-001", "New Address 123")
    assert updated.delivery_address == "New Address 123"
    assert updated.status == "PENDING"


def test_update_address_for_unknown_order_returns_none(connection):
    assert orders_repo.update_address(connection, "does-not-exist", "New Address 123") is None


def test_update_status_changes_status_only(connection):
    updated = orders_repo.update_status(connection, "order-006", "DELIVERED")
    assert updated.status == "DELIVERED"
    assert updated.delivery_address == "Carrera 45 # 12-34, Medellin"


def test_update_status_for_unknown_order_returns_none(connection):
    assert orders_repo.update_status(connection, "does-not-exist", "DELIVERED") is None


def test_create_returns_a_pending_order_with_a_single_product(connection):
    order = orders_repo.create(
        connection,
        client_id="1010101010",
        product_id="laptop-001",
        delivery_address="Calle Nueva 1",
        estimated_delivery_date="2026-09-30",
    )
    assert order.status == "PENDING"
    assert order.client_id == "1010101010"
    assert order.products == ["laptop-001"]
    assert order.delivery_address == "Calle Nueva 1"
    assert order.estimated_delivery_date == "2026-09-30"


def test_create_generates_a_new_unique_order_id(connection):
    first = orders_repo.create(
        connection, "1010101010", "laptop-001", "Address A", "2026-09-30"
    )
    second = orders_repo.create(
        connection, "1010101010", "laptop-001", "Address A", "2026-09-30"
    )
    assert first.order_id != second.order_id
    assert orders_repo.get(connection, first.order_id) is not None
    assert orders_repo.get(connection, second.order_id) is not None


def test_get_resolves_product_details_from_the_catalog(connection):
    order = orders_repo.get(connection, "order-001")
    assert [detail.model_dump() for detail in order.product_details] == [
        {
            "product_id": "laptop-002",
            "name": "CreatorBook Pro 15",
            "brand": "Zenda",
            "price": 4800000,
        }
    ]


def test_product_details_keeps_the_order_of_the_product_ids(connection):
    connection.execute(
        "UPDATE orders SET products = ? WHERE order_id = ?",
        ('["tablet-001", "laptop-001"]', "order-001"),
    )
    order = orders_repo.get(connection, "order-001")
    assert [detail.product_id for detail in order.product_details] == [
        "tablet-001",
        "laptop-001",
    ]


def test_product_details_keeps_an_entry_with_null_fields_for_a_product_off_the_catalog(
    connection,
):
    connection.execute("DELETE FROM products WHERE id = ?", ("laptop-002",))
    order = orders_repo.get(connection, "order-001")
    assert order.products == ["laptop-002"]
    assert [detail.model_dump() for detail in order.product_details] == [
        {"product_id": "laptop-002", "name": None, "brand": None, "price": None}
    ]


def test_list_by_client_resolves_product_details_too(connection):
    orders = orders_repo.list_by_client(connection, "1010101010")
    names = {order.order_id: order.product_details[0].name for order in orders}
    assert names["order-002"] == "SoundWave ANC"


def test_create_returns_an_order_carrying_product_details(connection):
    order = orders_repo.create(
        connection,
        client_id="1010101010",
        product_id="laptop-001",
        delivery_address="Calle Nueva 1",
        estimated_delivery_date="2026-09-30",
    )
    assert order.product_details[0].name == "UltraBook Air 14"


def test_list_all_returns_every_order_sorted_by_id(connection):
    orders = orders_repo.list_all(connection)
    assert [order.order_id for order in orders] == [
        "order-001",
        "order-002",
        "order-003",
        "order-004",
        "order-005",
        "order-006",
    ]


def test_resolve_product_details_for_an_empty_list_returns_empty(connection):
    assert orders_repo.resolve_product_details(connection, []) == []
