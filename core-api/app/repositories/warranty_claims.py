"""SQL repository for warranty claims."""
import sqlite3
import uuid

from app.schemas.warranty_claims import WarrantyClaim

# Fixed keyword list; the words themselves are Spanish because they match the customer's own
# Spanish description text, not a code identifier.
RISK_KEYWORDS = ("humo", "fuego", "choque", "explot", "chispa")


def create(
    connection: sqlite3.Connection,
    ticket_id: str,
    warranty_id: str | None,
    client_id: str,
    description: str,
    escalated: bool,
) -> WarrantyClaim | None:
    claim_id = f"claim-{uuid.uuid4().hex[:8]}"
    connection.execute(
        "INSERT INTO warranty_claims (claim_id, warranty_id, client_id, description, "
        "ticket_id, escalated, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (claim_id, warranty_id, client_id, description, ticket_id, int(escalated)),
    )
    connection.commit()
    return get(connection, claim_id)


def get(connection: sqlite3.Connection, claim_id: str) -> WarrantyClaim | None:
    row = connection.execute(
        "SELECT claim_id, warranty_id, client_id, description, ticket_id, escalated, "
        "created_at FROM warranty_claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_claim(row)


def descriptions_by_ticket_id(
    connection: sqlite3.Connection, ticket_ids: list[str]
) -> dict[str, str]:
    if not ticket_ids:
        return {}
    placeholders = ", ".join("?" for _ in ticket_ids)
    rows = connection.execute(
        f"SELECT ticket_id, description FROM warranty_claims WHERE ticket_id IN ({placeholders})",
        tuple(ticket_ids),
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def matches_risk_keyword(description: str) -> bool:
    lowered = description.lower()
    return any(keyword in lowered for keyword in RISK_KEYWORDS)


def _row_to_claim(row) -> WarrantyClaim:
    return WarrantyClaim(
        claim_id=row[0],
        warranty_id=row[1],
        client_id=row[2],
        description=row[3],
        ticket_id=row[4],
        escalated=bool(row[5]),
        created_at=row[6],
    )
