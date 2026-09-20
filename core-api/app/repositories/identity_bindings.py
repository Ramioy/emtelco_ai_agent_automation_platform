"""SQL repository for the link between an authenticated end user and the customer they are."""
import sqlite3


def get(connection: sqlite3.Connection, subject_id: str) -> str | None:
    row = connection.execute(
        "SELECT client_id FROM identity_bindings WHERE subject_id = ?", (subject_id,)
    ).fetchone()
    return row[0] if row is not None else None


def upsert(connection: sqlite3.Connection, subject_id: str, client_id: str) -> None:
    connection.execute(
        "INSERT INTO identity_bindings (subject_id, client_id) VALUES (?, ?) "
        "ON CONFLICT (subject_id) DO UPDATE SET client_id = excluded.client_id, "
        "updated_at = datetime('now')",
        (subject_id, client_id),
    )
    connection.commit()


def list_all(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        "SELECT subject_id, client_id, bound_at, updated_at FROM identity_bindings "
        "ORDER BY bound_at DESC"
    ).fetchall()
    return [
        {"subject_id": row[0], "client_id": row[1], "bound_at": row[2], "updated_at": row[3]}
        for row in rows
    ]
