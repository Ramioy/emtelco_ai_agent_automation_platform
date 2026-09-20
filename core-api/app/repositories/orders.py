"""SQL repository for orders."""
import json
import sqlite3
import uuid
from pathlib import Path

from app.schemas.orders import Order

SEED_PATH = Path(__file__).parent.parent / "data" / "seed" / "orders.json"


def seed(connection: sqlite3.Connection) -> None:
    """Load the orders fixture into the table once; a no-op on later calls. Requires
    clients_repo.seed() to have already run, since client_id is a foreign key here."""
    count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if count > 0:
        return
    orders = json.loads(SEED_PATH.read_text())
    connection.executemany(
        "INSERT INTO orders (order_id, client_id, status, estimated_delivery_date, "
        "delivery_address, products) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                order["order_id"],
                order["client_id"],
                order["status"],
                order["estimated_delivery_date"],
                order["delivery_address"],
                json.dumps(order["products"]),
            )
            for order in orders
        ],
    )
    connection.commit()


def get(connection: sqlite3.Connection, order_id: str) -> Order | None:
    row = connection.execute(
        "SELECT order_id, client_id, status, estimated_delivery_date, delivery_address, "
        "products FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_order(row)


def list_by_client(connection: sqlite3.Connection, client_id: str) -> list[Order]:
    rows = connection.execute(
        "SELECT order_id, client_id, status, estimated_delivery_date, delivery_address, "
        "products FROM orders WHERE client_id = ?",
        (client_id,),
    ).fetchall()
    return [_row_to_order(row) for row in rows]


def create(
    connection: sqlite3.Connection,
    client_id: str,
    product_id: str,
    delivery_address: str,
    estimated_delivery_date: str,
) -> Order | None:
    """Create a simulated order for a single product: one purchase = one product, no cart.
    Callers must already have validated that client_id exists and product_id has stock
    available."""
    order_id = f"order-{uuid.uuid4().hex[:8]}"
    connection.execute(
        "INSERT INTO orders (order_id, client_id, status, estimated_delivery_date, "
        "delivery_address, products) VALUES (?, ?, 'PENDING', ?, ?, ?)",
        (order_id, client_id, estimated_delivery_date, delivery_address, json.dumps([product_id])),
    )
    connection.commit()
    return get(connection, order_id)


def update_address(connection: sqlite3.Connection, order_id: str, new_address: str) -> Order | None:
    connection.execute(
        "UPDATE orders SET delivery_address = ? WHERE order_id = ?", (new_address, order_id)
    )
    connection.commit()
    return get(connection, order_id)


def update_status(connection: sqlite3.Connection, order_id: str, new_status: str) -> Order | None:
    connection.execute(
        "UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id)
    )
    connection.commit()
    return get(connection, order_id)


def _row_to_order(row) -> Order:
    return Order(
        order_id=row[0],
        client_id=row[1],
        status=row[2],
        estimated_delivery_date=row[3],
        delivery_address=row[4],
        products=json.loads(row[5]),
    )
