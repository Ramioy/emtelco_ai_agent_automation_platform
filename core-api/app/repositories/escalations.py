"""SQL repository for support tickets, shared by the manual escalation endpoint, the warranty
domain's automatic escalation and the operations console."""
import sqlite3

from app.schemas.escalations import AGENT_REQUEST, Escalation

COLUMNS = (
    "ticket_id, session_id, client_id, reason, priority, status, created_at, "
    "origin, assignee, resolution_note, updated_at, related_ticket_id"
)


def create(
    connection: sqlite3.Connection,
    ticket_id: str,
    session_id: str | None,
    client_id: str | None,
    reason: str,
    priority: str,
    origin: str = AGENT_REQUEST,
    related_ticket_id: str | None = None,
) -> Escalation | None:
    connection.execute(
        "INSERT INTO escalations (ticket_id, session_id, client_id, reason, priority, status, "
        "created_at, origin, related_ticket_id) "
        "VALUES (?, ?, ?, ?, ?, 'pending_agent', datetime('now'), ?, ?)",
        (ticket_id, session_id, client_id, reason, priority, origin, related_ticket_id),
    )
    connection.commit()
    return get(connection, ticket_id)


def get(connection: sqlite3.Connection, ticket_id: str) -> Escalation | None:
    row = connection.execute(
        f"SELECT {COLUMNS} FROM escalations WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()
    if row is None:
        return None
    return _row_to_escalation(row)


def list_all(connection: sqlite3.Connection) -> list[Escalation]:
    rows = connection.execute(
        f"SELECT {COLUMNS} FROM escalations ORDER BY created_at DESC, ticket_id DESC"
    ).fetchall()
    return [_row_to_escalation(row) for row in rows]


def list_by_client(connection: sqlite3.Connection, client_id: str) -> list[Escalation]:
    rows = connection.execute(
        f"SELECT {COLUMNS} FROM escalations WHERE client_id = ? "
        "ORDER BY created_at DESC, ticket_id DESC",
        (client_id,),
    ).fetchall()
    return [_row_to_escalation(row) for row in rows]


def update(
    connection: sqlite3.Connection,
    ticket_id: str,
    status: str,
    assignee: str | None,
    resolution_note: str | None,
) -> Escalation | None:
    """A None assignee or note leaves the stored one alone: taking a ticket must not wipe the
    note a previous pass wrote, and resolving must not wipe who took it."""
    connection.execute(
        "UPDATE escalations SET status = ?, "
        "assignee = COALESCE(?, assignee), "
        "resolution_note = COALESCE(?, resolution_note), "
        "updated_at = datetime('now') WHERE ticket_id = ?",
        (status, assignee, resolution_note, ticket_id),
    )
    connection.commit()
    return get(connection, ticket_id)


def _row_to_escalation(row) -> Escalation:
    return Escalation(
        ticket_id=row[0],
        session_id=row[1],
        client_id=row[2],
        reason=row[3],
        priority=row[4],
        status=row[5],
        created_at=row[6],
        origin=row[7] or AGENT_REQUEST,
        assignee=row[8],
        resolution_note=row[9],
        updated_at=row[10],
        related_ticket_id=row[11],
    )
