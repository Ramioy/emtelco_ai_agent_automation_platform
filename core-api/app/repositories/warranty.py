"""SQL repository for warranties."""
import calendar
import json
import sqlite3
import uuid
from datetime import date, timedelta
from pathlib import Path

from app.schemas.warranty import Warranty, WarrantyValidity

SEED_PATH = Path(__file__).parent.parent / "data" / "seed" / "warranties.json"

REINSTATED_MONTHS_REMAINING = 12


def seed(connection: sqlite3.Connection) -> None:
    """Load the warranties fixture into the table once; a no-op on later calls. Every seeded
    order carries its warranty except order-001, left uncovered on purpose: absence is how the
    "no warranty registered" case is represented, not a separate flag, and the agent has to be
    able to report it."""
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


def create(
    connection: sqlite3.Connection,
    order_id: str,
    product_id: str,
    coverage_months: int,
    purchase_date: str,
) -> Warranty:
    """Issue the warranty that comes with a sale. Called by order creation, so an order the
    agent takes is claimable from the moment it exists."""
    warranty_id = f"warranty-{uuid.uuid4().hex[:8]}"
    connection.execute(
        "INSERT INTO warranties (warranty_id, order_id, product_id, coverage_months, "
        "purchase_date) VALUES (?, ?, ?, ?, ?)",
        (warranty_id, order_id, product_id, coverage_months, purchase_date),
    )
    connection.commit()
    return get_by_id(connection, warranty_id)


def update(
    connection: sqlite3.Connection,
    warranty_id: str,
    coverage_months: int | None = None,
    purchase_date: str | None = None,
) -> Warranty | None:
    """Both columns validity is computed from, so an operator can put a warranty into any
    state instead of only the two the shortcut endpoints reach."""
    assignments = []
    params: list[str | int] = []
    if coverage_months is not None:
        assignments.append("coverage_months = ?")
        params.append(coverage_months)
    if purchase_date is not None:
        assignments.append("purchase_date = ?")
        params.append(purchase_date)
    if assignments:
        params.append(warranty_id)
        connection.execute(
            f"UPDATE warranties SET {', '.join(assignments)} WHERE warranty_id = ?", params
        )
        connection.commit()
    return get_by_id(connection, warranty_id)


def get(connection: sqlite3.Connection, order_id: str, product_id: str) -> Warranty | None:
    row = connection.execute(
        "SELECT warranty_id, order_id, product_id, coverage_months, purchase_date "
        "FROM warranties WHERE order_id = ? AND product_id = ?",
        (order_id, product_id),
    ).fetchone()
    if row is None:
        return None
    return _row_to_warranty(row)


def list_all(connection: sqlite3.Connection) -> list[Warranty]:
    rows = connection.execute(
        "SELECT warranty_id, order_id, product_id, coverage_months, purchase_date "
        "FROM warranties ORDER BY warranty_id"
    ).fetchall()
    return [_row_to_warranty(row) for row in rows]


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


def purchase_date_for_termination(warranty: Warranty, today: date | None = None) -> str:
    """Zero coverage only reads as expired once the purchase is in the past, and an order the
    agent took today is not: its window would close exactly today, which still counts as
    covered. Backdating such a record by one day is the smallest change that closes it."""
    today = today or date.today()
    purchase_date = date.fromisoformat(warranty.purchase_date)
    return min(purchase_date, today - timedelta(days=1)).isoformat()


def coverage_for_reinstatement(warranty: Warranty, today: date | None = None) -> int:
    """Coverage that puts the warranty back under REINSTATED_MONTHS_REMAINING months of
    remaining validity, still counted from the original purchase date: that date is a fact of
    the order and is never rewritten, so coverage is the only knob, exactly as in a
    termination."""
    today = today or date.today()
    purchase_date = date.fromisoformat(warranty.purchase_date)
    target_expiry = _add_months(today, REINSTATED_MONTHS_REMAINING)
    months = _months_between(purchase_date, target_expiry)
    if _add_months(purchase_date, months) < target_expiry:
        months += 1
    return max(0, months)


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
