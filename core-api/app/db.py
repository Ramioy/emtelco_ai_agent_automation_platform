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


def get_connection(database_path: str | Path) -> sqlite3.Connection:
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
    clients_repo.seed(connection)
    catalog_repo.seed(connection)
    orders_repo.seed(connection)
    warranty_repo.seed(connection)
    return connection


def get_db() -> Iterator[sqlite3.Connection]:
    connection = get_connection(get_settings().database_path)
    try:
        yield connection
    finally:
        connection.close()
