"""SQL repository for escalations to a human agent, shared by the manual escalation endpoint
and the warranty domain's automatic escalation."""
import sqlite3

from app.schemas.escalations import Escalation


def create(
    connection: sqlite3.Connection,
    ticket_id: str,
    session_id: str | None,
    client_id: str | None,
    reason: str,
    priority: str,
) -> Escalation | None:
    connection.execute(
        "INSERT INTO escalations (ticket_id, session_id, client_id, reason, priority, status, "
        "created_at) VALUES (?, ?, ?, ?, ?, 'pending_agent', datetime('now'))",
        (ticket_id, session_id, client_id, reason, priority),
    )
    connection.commit()
    return get(connection, ticket_id)


def get(connection: sqlite3.Connection, ticket_id: str) -> Escalation | None:
    row = connection.execute(
        "SELECT ticket_id, session_id, client_id, reason, priority, status, created_at "
        "FROM escalations WHERE ticket_id = ?",
        (ticket_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_escalation(row)


def _row_to_escalation(row) -> Escalation:
    return Escalation(
        ticket_id=row[0],
        session_id=row[1],
        client_id=row[2],
        reason=row[3],
        priority=row[4],
        status=row[5],
        created_at=row[6],
    )
