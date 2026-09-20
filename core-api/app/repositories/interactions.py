"""SQL repository for the interactions audit log."""
import json
import sqlite3


def log(
    connection: sqlite3.Connection,
    session_id: str,
    client_id: str | None,
    interaction_type: str,
    detail: dict,
) -> None:
    connection.execute(
        "INSERT INTO interactions (session_id, client_id, type, detail) VALUES (?, ?, ?, ?)",
        (session_id, client_id, interaction_type, json.dumps(detail)),
    )
    connection.commit()


def list_sessions_for_client(connection: sqlite3.Connection, client_id: str) -> list[dict]:
    sessions = connection.execute(
        "SELECT session_id, started_at FROM sessions WHERE client_id = ? ORDER BY started_at",
        (client_id,),
    ).fetchall()

    result = []
    for session_id, started_at in sessions:
        types = connection.execute(
            "SELECT DISTINCT type FROM interactions WHERE session_id = ? ORDER BY type",
            (session_id,),
        ).fetchall()
        summary = ", ".join(row[0] for row in types) if types else "no interactions logged"
        result.append({"session_id": session_id, "started_at": started_at, "summary": summary})
    return result
