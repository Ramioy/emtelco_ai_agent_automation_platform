"""Tests for the warranty SQL repository, against a temporary SQLite database."""
from datetime import date

import pytest

from app.db import init_db
from app.repositories import warranty as warranty_repo
from app.schemas.warranty import Warranty


@pytest.fixture
def connection(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def test_init_db_seeds_warranties_from_fixture(connection):
    count = connection.execute("SELECT COUNT(*) FROM warranties").fetchone()[0]
    assert count > 0


def test_seed_is_idempotent(connection):
    before = connection.execute("SELECT COUNT(*) FROM warranties").fetchone()[0]
    warranty_repo.seed(connection)
    after = connection.execute("SELECT COUNT(*) FROM warranties").fetchone()[0]
    assert before == after


def test_get_returns_none_when_no_warranty_row_exists(connection):
    # order-001/laptop-002 is a real seeded order with no warranty fixture entry at all.
    assert warranty_repo.get(connection, "order-001", "laptop-002") is None


def test_get_returns_the_matching_warranty(connection):
    warranty = warranty_repo.get(connection, "order-002", "headphones-001")
    assert warranty.warranty_id == "warranty-001"
    assert warranty.coverage_months == 36
    assert warranty.purchase_date == "2026-07-01"


def test_get_requires_both_order_id_and_product_id_to_match(connection):
    assert warranty_repo.get(connection, "order-002", "tablet-001") is None
    assert warranty_repo.get(connection, "order-003", "headphones-001") is None


def test_compute_validity_is_valid_within_coverage_window():
    warranty = Warranty(
        warranty_id="w", order_id="o", product_id="p",
        coverage_months=12, purchase_date="2026-01-01",
    )
    validity = warranty_repo.compute_validity(warranty, today=date(2026, 6, 15))
    assert validity.is_valid is True
    assert validity.months_remaining == 6


def test_compute_validity_clamps_end_of_month_when_adding_coverage_months():
    # Jan 31 + 1 month has no literal Feb 31; must clamp to the last day of a shorter month.
    warranty = Warranty(
        warranty_id="w", order_id="o", product_id="p",
        coverage_months=1, purchase_date="2023-01-31",
    )
    assert warranty_repo.compute_validity(warranty, today=date(2023, 2, 28)).is_valid is True
    assert warranty_repo.compute_validity(warranty, today=date(2023, 3, 1)).is_valid is False


def test_compute_validity_is_invalid_after_coverage_window_expires():
    warranty = Warranty(
        warranty_id="w", order_id="o", product_id="p",
        coverage_months=12, purchase_date="2023-01-01",
    )
    validity = warranty_repo.compute_validity(warranty, today=date(2026, 9, 19))
    assert validity.is_valid is False
    assert validity.months_remaining == 0


def test_compute_validity_on_the_exact_expiry_date_is_still_valid():
    warranty = Warranty(
        warranty_id="w", order_id="o", product_id="p",
        coverage_months=1, purchase_date="2026-01-01",
    )
    validity = warranty_repo.compute_validity(warranty, today=date(2026, 2, 1))
    assert validity.is_valid is True
    assert validity.months_remaining == 0


def test_compute_validity_the_day_after_expiry_is_invalid():
    warranty = Warranty(
        warranty_id="w", order_id="o", product_id="p",
        coverage_months=1, purchase_date="2026-01-01",
    )
    validity = warranty_repo.compute_validity(warranty, today=date(2026, 2, 2))
    assert validity.is_valid is False


def test_seeded_warranty_for_order_002_is_currently_valid(connection):
    """Checks the seeded valid warranty against the real current date, not a pinned one."""
    warranty = warranty_repo.get(connection, "order-002", "headphones-001")
    validity = warranty_repo.compute_validity(warranty)
    assert validity.is_valid is True


def test_seeded_warranty_for_order_003_is_currently_expired(connection):
    """Checks the seeded expired warranty against the real current date, not a pinned one."""
    warranty = warranty_repo.get(connection, "order-003", "tablet-001")
    validity = warranty_repo.compute_validity(warranty)
    assert validity.is_valid is False


def test_get_by_id_returns_the_matching_warranty(connection):
    warranty = warranty_repo.get_by_id(connection, "warranty-002")
    assert warranty.order_id == "order-003"
    assert warranty.product_id == "tablet-001"


def test_get_by_id_returns_none_for_unknown_warranty_id(connection):
    assert warranty_repo.get_by_id(connection, "does-not-exist") is None


def test_update_coverage_months_to_zero_makes_a_valid_warranty_expired(connection):
    warranty = warranty_repo.update_coverage_months(connection, "warranty-001", 0)
    assert warranty.coverage_months == 0
    assert warranty_repo.compute_validity(warranty).is_valid is False


def test_update_coverage_months_for_unknown_warranty_id_returns_none(connection):
    assert warranty_repo.update_coverage_months(connection, "does-not-exist", 0) is None
