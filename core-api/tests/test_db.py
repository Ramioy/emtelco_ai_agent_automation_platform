"""Tests for SQLite schema initialization."""
from app.db import init_db

EXPECTED_TABLES = {
    "clients",
    "products",
    "orders",
    "warranties",
    "warranty_claims",
    "escalations",
    "sessions",
    "client_memory",
    "interactions",
}


def test_init_db_creates_all_expected_tables(tmp_path):
    connection = init_db(tmp_path / "test.db")
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {row[0] for row in rows}
    connection.close()
    assert EXPECTED_TABLES <= table_names


def test_init_db_seeds_clients_before_orders_so_the_foreign_key_holds(tmp_path):
    """clients/catalog/orders seeding each has its own repo-level test; this one only
    guards db.py's orchestration order, since orders.client_id is a real foreign key."""
    connection = init_db(tmp_path / "test.db")
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("clients", "products", "orders")
    }
    connection.close()
    assert all(count > 0 for count in counts.values())


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path).close()
    connection = init_db(db_path)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    connection.close()
    assert EXPECTED_TABLES <= {row[0] for row in rows}
