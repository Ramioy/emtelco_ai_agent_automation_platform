"""SQL repository for cross-session client memory."""
import json
import sqlite3

from app.schemas.client_memory import ClientMemory
from app.schemas.sessions import Session


def get(connection: sqlite3.Connection, client_id: str) -> ClientMemory | None:
    row = _fetch_row(connection, client_id)
    return _row_to_memory(row) if row else None


def upsert_from_session(connection: sqlite3.Connection, session: Session) -> ClientMemory:
    if session.client_id is None:
        raise ValueError("session must be linked to a client_id before merging into memory")

    existing = get(connection, session.client_id)
    if existing is None:
        merged = ClientMemory(
            client_id=session.client_id,
            client_name=session.client_name,
            mentioned_budgets=list(session.mentioned_budgets),
            last_order_checked=session.last_order_checked,
            products_viewed=list(session.products_viewed),
            preferences=list(session.preferences),
            last_session_id=session.session_id,
        )
    else:
        merged = ClientMemory(
            client_id=session.client_id,
            client_name=session.client_name or existing.client_name,
            mentioned_budgets=_accumulate_ordered(
                existing.mentioned_budgets, session.mentioned_budgets
            ),
            last_order_checked=session.last_order_checked or existing.last_order_checked,
            products_viewed=_accumulate_unique(existing.products_viewed, session.products_viewed),
            preferences=_accumulate_unique(existing.preferences, session.preferences),
            last_session_id=session.session_id,
        )

    connection.execute(
        """
        INSERT INTO client_memory
            (client_id, client_name, mentioned_budgets, last_order_checked,
             products_viewed, preferences, last_session_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(client_id) DO UPDATE SET
            client_name = excluded.client_name,
            mentioned_budgets = excluded.mentioned_budgets,
            last_order_checked = excluded.last_order_checked,
            products_viewed = excluded.products_viewed,
            preferences = excluded.preferences,
            last_session_id = excluded.last_session_id,
            updated_at = excluded.updated_at
        """,
        (
            merged.client_id,
            merged.client_name,
            json.dumps(merged.mentioned_budgets),
            merged.last_order_checked,
            json.dumps(merged.products_viewed),
            json.dumps(merged.preferences),
            merged.last_session_id,
        ),
    )
    connection.commit()
    return merged


def _accumulate_unique(existing: list, new_items: list) -> list:
    """Union that keeps first-seen order; order does not carry meaning for these fields."""
    merged = list(existing)
    for item in new_items:
        if item not in merged:
            merged.append(item)
    return merged


def _accumulate_ordered(existing: list, new_items: list) -> list:
    """Fold in new_items, skipping only an immediate repeat of the last value."""
    merged = list(existing)
    for item in new_items:
        if not merged or merged[-1] != item:
            merged.append(item)
    return merged


def _fetch_row(connection: sqlite3.Connection, client_id: str):
    return connection.execute(
        """
        SELECT client_id, client_name, mentioned_budgets, last_order_checked,
               products_viewed, preferences, last_session_id
        FROM client_memory WHERE client_id = ?
        """,
        (client_id,),
    ).fetchone()


def _row_to_memory(row) -> ClientMemory:
    return ClientMemory(
        client_id=row[0],
        client_name=row[1],
        mentioned_budgets=json.loads(row[2]) if row[2] else [],
        last_order_checked=row[3],
        products_viewed=json.loads(row[4]) if row[4] else [],
        preferences=json.loads(row[5]) if row[5] else [],
        last_session_id=row[6],
    )
