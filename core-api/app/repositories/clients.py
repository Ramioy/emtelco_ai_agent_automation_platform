"""SQL repository for the clients table."""
import json
import sqlite3
from pathlib import Path

from app.schemas.clients import Client, ClientCreate

SEED_PATH = Path(__file__).parent.parent / "data" / "seed" / "clients.json"


def seed(connection: sqlite3.Connection) -> None:
    """Seed a couple of demo clients so the orders fixture has valid client_id foreign keys,
    and an order-tracking conversation is demoable without a prior registration."""
    count = connection.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    if count > 0:
        return
    clients = json.loads(SEED_PATH.read_text())
    connection.executemany(
        "INSERT INTO clients (client_id, full_name, phone, email) VALUES (?, ?, ?, ?)",
        [
            (client["client_id"], client["full_name"], client["phone"], client["email"])
            for client in clients
        ],
    )
    connection.commit()


def exists(connection: sqlite3.Connection, client_id: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM clients WHERE client_id = ?", (client_id,)
    ).fetchone()
    return row is not None


def insert(connection: sqlite3.Connection, client: ClientCreate) -> Client:
    connection.execute(
        "INSERT INTO clients (client_id, full_name, phone, email) VALUES (?, ?, ?, ?)",
        (client.client_id, client.full_name, client.phone, client.email),
    )
    connection.commit()
    return Client(**client.model_dump())


def get(connection: sqlite3.Connection, client_id: str) -> Client | None:
    row = connection.execute(
        "SELECT client_id, full_name, phone, email FROM clients WHERE client_id = ?",
        (client_id,),
    ).fetchone()
    if row is None:
        return None
    return Client(client_id=row[0], full_name=row[1], phone=row[2], email=row[3])
