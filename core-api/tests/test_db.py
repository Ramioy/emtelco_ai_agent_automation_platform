"""Tests for SQLite schema initialization."""
import sqlite3

from app.db import ADDED_COLUMNS, get_connection, init_db

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
    "identity_bindings",
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


def test_init_db_adds_columns_missing_from_a_database_created_before_them(tmp_path):
    """CREATE TABLE IF NOT EXISTS leaves an existing table alone, so a volume written by an
    earlier build would otherwise keep an escalations table with no lifecycle columns."""
    db_path = tmp_path / "old.db"
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE escalations (ticket_id TEXT PRIMARY KEY, session_id TEXT, "
        "client_id TEXT, reason TEXT, priority TEXT, status TEXT, created_at TEXT)"
    )
    legacy.commit()
    legacy.close()

    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE products (id TEXT PRIMARY KEY, category TEXT, name TEXT, brand TEXT, "
        "price INTEGER, specs TEXT, stock INTEGER)"
    )
    legacy.execute(
        "INSERT INTO products VALUES ('laptop-001','laptop','UltraBook','Zenda',1,'{}',5)"
    )
    legacy.commit()
    legacy.close()

    connection = init_db(db_path)
    for table in ("escalations", "products"):
        present = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        assert {name for name, _ in ADDED_COLUMNS[table]} <= present, table
    # The seed is count-gated, so an already-populated products table keeps its own rows and
    # the new column has to be usable on them, not only on freshly seeded ones.
    row = connection.execute(
        "SELECT warranty_months FROM products WHERE id = 'laptop-001'"
    ).fetchone()
    connection.close()
    assert row == (12,)


def test_adding_columns_twice_changes_nothing(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path).close()
    connection = get_connection(db_path)
    before = connection.execute("PRAGMA table_info(escalations)").fetchall()
    init_db(db_path).close()
    after = connection.execute("PRAGMA table_info(escalations)").fetchall()
    connection.close()
    assert before == after
