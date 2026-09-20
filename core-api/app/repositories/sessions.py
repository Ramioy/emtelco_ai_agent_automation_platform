"""SQL repository for session-scoped memory."""
import json
import sqlite3

from app.repositories import client_memory as client_memory_repo
from app.repositories import interactions as interactions_repo
from app.schemas.sessions import Session, SessionUpdate


def get_or_create(connection: sqlite3.Connection, session_id: str) -> Session:
    row = _fetch_row(connection, session_id)
    if row is None:
        connection.execute("INSERT INTO sessions (session_id) VALUES (?)", (session_id,))
        connection.commit()
        row = _fetch_row(connection, session_id)
    return _row_to_session(row)


def link_client(connection: sqlite3.Connection, session_id: str, client_id: str) -> Session:
    """Link a session to a known client_id and fold whatever this session already
    accumulated into client_memory right away, not on the next PUT."""
    get_or_create(connection, session_id)
    connection.execute(
        "UPDATE sessions SET client_id = ? WHERE session_id = ?", (client_id, session_id)
    )
    connection.commit()
    interactions_repo.log(
        connection, session_id, client_id, "note", {"field": "client_id", "value": client_id}
    )
    session = _current(connection, session_id)
    client_memory_repo.upsert_from_session(connection, session)
    return session


def record_products_viewed(
    connection: sqlite3.Connection, session_id: str, product_ids: list[str]
) -> Session:
    """Append the given ids to products_viewed in a single batched write, used by
    GET /catalog/products's side effect instead of one full update() round trip per
    product."""
    get_or_create(connection, session_id)
    session = _current(connection, session_id)
    new_ids = [product_id for product_id in product_ids if product_id not in session.products_viewed]
    if not new_ids:
        return session

    updated_products = session.products_viewed + new_ids
    connection.execute(
        "UPDATE sessions SET products_viewed = ?, last_activity_at = datetime('now') "
        "WHERE session_id = ?",
        (json.dumps(updated_products), session_id),
    )
    connection.commit()
    for product_id in new_ids:
        interactions_repo.log(
            connection, session_id, session.client_id, "note",
            {"field": "product_viewed", "value": product_id},
        )

    session = _current(connection, session_id)
    if session.client_id is not None:
        client_memory_repo.upsert_from_session(connection, session)
    return session


def record_last_order_checked(
    connection: sqlite3.Connection, session_id: str, order_id: str
) -> Session:
    """Overwrite last_order_checked with the given order id, used by
    GET /orders/{order_id}/status's side effect."""
    return update(connection, session_id, SessionUpdate(last_order_checked=order_id))


def update(connection: sqlite3.Connection, session_id: str, changes: SessionUpdate) -> Session:
    get_or_create(connection, session_id)
    client_id = _current(connection, session_id).client_id

    if changes.client_name is not None:
        connection.execute(
            "UPDATE sessions SET client_name = ? WHERE session_id = ?",
            (changes.client_name, session_id),
        )
        interactions_repo.log(
            connection,
            session_id,
            client_id,
            "note",
            {"field": "client_name", "value": changes.client_name},
        )
    if changes.last_order_checked is not None:
        connection.execute(
            "UPDATE sessions SET last_order_checked = ? WHERE session_id = ?",
            (changes.last_order_checked, session_id),
        )
        interactions_repo.log(
            connection,
            session_id,
            client_id,
            "note",
            {"field": "last_order_checked", "value": changes.last_order_checked},
        )
    if changes.mentioned_budget is not None:
        budgets = _current(connection, session_id).mentioned_budgets
        if not budgets or budgets[-1] != changes.mentioned_budget:
            budgets.append(changes.mentioned_budget)
        connection.execute(
            "UPDATE sessions SET mentioned_budgets = ? WHERE session_id = ?",
            (json.dumps(budgets), session_id),
        )
        interactions_repo.log(
            connection, session_id, client_id, "budget", {"value": changes.mentioned_budget}
        )
    if changes.product_viewed is not None:
        products = _current(connection, session_id).products_viewed
        if changes.product_viewed not in products:
            products.append(changes.product_viewed)
        connection.execute(
            "UPDATE sessions SET products_viewed = ? WHERE session_id = ?",
            (json.dumps(products), session_id),
        )
        interactions_repo.log(
            connection,
            session_id,
            client_id,
            "note",
            {"field": "product_viewed", "value": changes.product_viewed},
        )
    if changes.preference is not None:
        preferences = _current(connection, session_id).preferences
        if changes.preference not in preferences:
            preferences.append(changes.preference)
        connection.execute(
            "UPDATE sessions SET preferences = ? WHERE session_id = ?",
            (json.dumps(preferences), session_id),
        )
        interactions_repo.log(
            connection, session_id, client_id, "preference", {"value": changes.preference}
        )

    connection.execute(
        "UPDATE sessions SET last_activity_at = datetime('now') WHERE session_id = ?",
        (session_id,),
    )
    connection.commit()
    session = _current(connection, session_id)
    if session.client_id is not None:
        client_memory_repo.upsert_from_session(connection, session)
    return session


def _current(connection: sqlite3.Connection, session_id: str) -> Session:
    return _row_to_session(_fetch_row(connection, session_id))


def _fetch_row(connection: sqlite3.Connection, session_id: str):
    return connection.execute(
        """
        SELECT session_id, client_id, client_name, mentioned_budgets,
               last_order_checked, products_viewed, preferences
        FROM sessions WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()


def _row_to_session(row) -> Session:
    return Session(
        session_id=row[0],
        client_id=row[1],
        client_name=row[2],
        mentioned_budgets=json.loads(row[3]) if row[3] else [],
        last_order_checked=row[4],
        products_viewed=json.loads(row[5]) if row[5] else [],
        preferences=json.loads(row[6]) if row[6] else [],
    )
