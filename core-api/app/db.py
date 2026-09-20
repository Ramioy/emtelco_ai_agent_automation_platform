"""SQLite connection helpers: schema initialization and per-request connections."""
import sqlite3
from pathlib import Path
from typing import Iterator

from app.config import get_settings
from app.repositories import catalog as catalog_repo
from app.repositories import clients as clients_repo
from app.repositories import orders as orders_repo
from app.repositories import warranty as warranty_repo

SCHEMA_PATH = Path(__file__).parent / "data" / "schema.sql"

# CREATE TABLE IF NOT EXISTS leaves an already-created table alone, so columns added after a
# volume was first written need their own idempotent step.
ADDED_COLUMNS = {
    "products": (("warranty_months", "INTEGER NOT NULL DEFAULT 12"),),
    "escalations": (
        ("origin", "TEXT NOT NULL DEFAULT 'agent_request'"),
        ("assignee", "TEXT"),
        ("resolution_note", "TEXT"),
        ("updated_at", "TEXT"),
    ),
}


def get_connection(database_path: str | Path) -> sqlite3.Connection:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    # FastAPI runs sync endpoints/dependencies in a thread pool, so a connection
    # created for one request can be handed off across threads; there is no real
    # concurrent access to guard against at this scale (a single demo session).
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db(database_path: str | Path) -> sqlite3.Connection:
    connection = get_connection(database_path)
    connection.executescript(SCHEMA_PATH.read_text())
    connection.commit()
    add_missing_columns(connection)
    clients_repo.seed(connection)
    catalog_repo.seed(connection)
    orders_repo.seed(connection)
    warranty_repo.seed(connection)
    return connection


def add_missing_columns(connection: sqlite3.Connection) -> None:
    for table, columns in ADDED_COLUMNS.items():
        present = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not present:
            continue
        for name, definition in columns:
            if name not in present:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    connection.commit()


def get_db() -> Iterator[sqlite3.Connection]:
    connection = get_connection(get_settings().database_path)
    try:
        yield connection
    finally:
        connection.close()
