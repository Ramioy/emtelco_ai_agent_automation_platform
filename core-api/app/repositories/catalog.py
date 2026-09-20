"""SQL repository for the products catalog."""
import json
import sqlite3
from pathlib import Path

from app.schemas.catalog import Product

SEED_PATH = Path(__file__).parent.parent / "data" / "seed" / "products.json"


def seed(connection: sqlite3.Connection) -> None:
    """Load the products fixture into the table once; a no-op on later calls, since
    init_db() runs on every app startup and must stay idempotent."""
    count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    if count > 0:
        return
    products = json.loads(SEED_PATH.read_text())
    connection.executemany(
        "INSERT INTO products (id, category, name, brand, price, specs, stock, "
        "warranty_months) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                product["id"],
                product["category"],
                product["name"],
                product["brand"],
                product["price"],
                json.dumps(product["specs"]),
                product["stock"],
                product["warranty_months"],
            )
            for product in products
        ],
    )
    connection.commit()


def list_products(
    connection: sqlite3.Connection,
    category: str | None = None,
    max_budget: int | None = None,
) -> list[Product]:
    clauses = []
    params: list[str | int] = []
    if category is not None:
        clauses.append("category = ?")
        params.append(category)
    if max_budget is not None:
        clauses.append("price <= ?")
        params.append(max_budget)

    query = "SELECT id, category, name, brand, price, specs, stock, warranty_months FROM products"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    rows = connection.execute(query, params).fetchall()
    return [_row_to_product(row) for row in rows]


def get_by_ids(connection: sqlite3.Connection, ids: list[str]) -> list[Product]:
    placeholders = ",".join("?" for _ in ids)
    rows = connection.execute(
        "SELECT id, category, name, brand, price, specs, stock, warranty_months "
        f"FROM products WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    return [_row_to_product(row) for row in rows]


def decrement_stock(connection: sqlite3.Connection, product_id: str) -> None:
    """Decrement stock by 1 for a completed purchase. Callers must already have validated
    stock > 0 for this product_id."""
    connection.execute("UPDATE products SET stock = stock - 1 WHERE id = ?", (product_id,))
    connection.commit()


def compute_key_differences(products: list[Product]) -> list[str]:
    differences = []
    for field in ("category", "brand", "price", "stock", "warranty_months"):
        values = {getattr(product, field) for product in products}
        if len(values) > 1:
            differences.append(field)

    spec_keys: set[str] = set()
    for product in products:
        spec_keys.update(product.specs.keys())
    for key in sorted(spec_keys):
        values = {product.specs.get(key) for product in products}
        if len(values) > 1:
            differences.append(f"specs.{key}")

    return differences


def _row_to_product(row) -> Product:
    return Product(
        id=row[0],
        category=row[1],
        name=row[2],
        brand=row[3],
        price=row[4],
        specs=json.loads(row[5]),
        stock=row[6],
        warranty_months=row[7],
    )
