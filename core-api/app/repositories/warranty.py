"""SQL repository for warranties."""
import calendar
import json
import sqlite3
from datetime import date
from pathlib import Path

from app.schemas.warranty import Warranty, WarrantyValidity

SEED_PATH = Path(__file__).parent.parent / "data" / "seed" / "warranties.json"


def seed(connection: sqlite3.Connection) -> None:
    """Load the warranties fixture into the table once; a no-op on later calls. Not every
    order/product has a row here on purpose: absence is how the "no warranty registered"
    case is represented, not a separate flag."""
    count = connection.execute("SELECT COUNT(*) FROM warranties").fetchone()[0]
    if count > 0:
        return
    warranties = json.loads(SEED_PATH.read_text())
    connection.executemany(
        "INSERT INTO warranties (warranty_id, order_id, product_id, coverage_months, "
        "purchase_date) VALUES (?, ?, ?, ?, ?)",
        [
            (
                warranty["warranty_id"],
                warranty["order_id"],
                warranty["product_id"],
                warranty["coverage_months"],
                warranty["purchase_date"],
            )
            for warranty in warranties
        ],
    )
    connection.commit()


def get(connection: sqlite3.Connection, order_id: str, product_id: str) -> Warranty | None:
    row = connection.execute(
        "SELECT warranty_id, order_id, product_id, coverage_months, purchase_date "
        "FROM warranties WHERE order_id = ? AND product_id = ?",
        (order_id, product_id),
    ).fetchone()
    if row is None:
        return None
    return _row_to_warranty(row)


def get_by_id(connection: sqlite3.Connection, warranty_id: str) -> Warranty | None:
    row = connection.execute(
        "SELECT warranty_id, order_id, product_id, coverage_months, purchase_date "
        "FROM warranties WHERE warranty_id = ?",
        (warranty_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_warranty(row)


def update_coverage_months(
    connection: sqlite3.Connection, warranty_id: str, coverage_months: int
) -> Warranty | None:
    connection.execute(
        "UPDATE warranties SET coverage_months = ? WHERE warranty_id = ?",
        (coverage_months, warranty_id),
    )
    connection.commit()
    return get_by_id(connection, warranty_id)


def compute_validity(warranty: Warranty, today: date | None = None) -> WarrantyValidity:
    """is_valid = today <= purchase_date + coverage_months, computed at query time and never
    stored, so it can never drift stale. `today` is overridable for deterministic tests;
    defaults to the real current date."""
    today = today or date.today()
    purchase_date = date.fromisoformat(warranty.purchase_date)
    expiry_date = _add_months(purchase_date, warranty.coverage_months)
    return WarrantyValidity(
        is_valid=today <= expiry_date,
        months_remaining=max(0, _months_between(today, expiry_date)),
    )


def _add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _months_between(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return months


def _row_to_warranty(row) -> Warranty:
    return Warranty(
        warranty_id=row[0],
        order_id=row[1],
        product_id=row[2],
        coverage_months=row[3],
        purchase_date=row[4],
    )
