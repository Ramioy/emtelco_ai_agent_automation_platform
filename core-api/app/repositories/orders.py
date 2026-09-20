"""SQL repository for orders."""
import json
import sqlite3
import uuid
from pathlib import Path

from app.repositories import catalog as catalog_repo
from app.schemas.orders import Order, OrderProduct

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
    return _row_to_order(connection, row)


def list_all(connection: sqlite3.Connection) -> list[Order]:
    rows = connection.execute(
        "SELECT order_id, client_id, status, estimated_delivery_date, delivery_address, "
        "products FROM orders ORDER BY order_id"
    ).fetchall()
    return [_row_to_order(connection, row) for row in rows]


def list_by_client(connection: sqlite3.Connection, client_id: str) -> list[Order]:
    rows = connection.execute(
        "SELECT order_id, client_id, status, estimated_delivery_date, delivery_address, "
        "products FROM orders WHERE client_id = ?",
        (client_id,),
    ).fetchall()
    return [_row_to_order(connection, row) for row in rows]


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


def resolve_product_details(
    connection: sqlite3.Connection, product_ids: list[str]
) -> list[OrderProduct]:
    """Ids an order references but the catalog no longer has still get an entry, with the
    commercial fields left null, so the order never silently loses a line."""
    if not product_ids:
        return []
    found = {product.id: product for product in catalog_repo.get_by_ids(connection, product_ids)}
    details = []
    for product_id in product_ids:
        product = found.get(product_id)
        if product is None:
            details.append(OrderProduct(product_id=product_id))
        else:
            details.append(
                OrderProduct(
                    product_id=product.id,
                    name=product.name,
                    brand=product.brand,
                    price=product.price,
                )
            )
    return details


def _row_to_order(connection: sqlite3.Connection, row) -> Order:
    products = json.loads(row[5])
    return Order(
        order_id=row[0],
        client_id=row[1],
        status=row[2],
        estimated_delivery_date=row[3],
        delivery_address=row[4],
        products=products,
        product_details=resolve_product_details(connection, products),
    )
