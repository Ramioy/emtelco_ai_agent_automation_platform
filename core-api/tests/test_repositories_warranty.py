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


def test_list_all_returns_every_seeded_warranty_sorted_by_id(connection):
    warranties = warranty_repo.list_all(connection)
    assert [warranty.warranty_id for warranty in warranties] == [
        "warranty-001",
        "warranty-002",
        "warranty-003",
        "warranty-004",
        "warranty-005",
    ]


def test_list_all_returns_empty_when_there_are_no_warranties(connection):
    connection.execute("DELETE FROM warranties")
    assert warranty_repo.list_all(connection) == []


def _unexpired(purchase_date: str) -> Warranty:
    return Warranty(
        warranty_id="w", order_id="o", product_id="p",
        coverage_months=0, purchase_date=purchase_date,
    )


def test_coverage_for_reinstatement_makes_a_long_expired_warranty_valid_again():
    warranty = _unexpired("2023-01-01")
    today = date(2026, 9, 19)
    assert warranty_repo.compute_validity(warranty, today=today).is_valid is False
    coverage = warranty_repo.coverage_for_reinstatement(warranty, today=today)
    reinstated = warranty.model_copy(update={"coverage_months": coverage})
    assert warranty_repo.compute_validity(reinstated, today=today).is_valid is True


def test_coverage_for_reinstatement_leaves_the_standard_window_whatever_the_purchase_date():
    today = date(2026, 9, 19)
    for purchase_date in ("2019-03-01", "2023-01-25", "2026-09-19", "2027-01-01"):
        warranty = _unexpired(purchase_date)
        coverage = warranty_repo.coverage_for_reinstatement(warranty, today=today)
        validity = warranty_repo.compute_validity(
            warranty.model_copy(update={"coverage_months": coverage}), today=today
        )
        assert validity.is_valid is True
        assert validity.months_remaining == warranty_repo.REINSTATED_MONTHS_REMAINING


def test_coverage_for_reinstatement_counts_from_the_purchase_date_not_from_today():
    today = date(2026, 9, 19)
    older = warranty_repo.coverage_for_reinstatement(_unexpired("2019-03-01"), today=today)
    recent = warranty_repo.coverage_for_reinstatement(_unexpired("2026-03-01"), today=today)
    assert older > recent


def test_create_issues_a_warranty_that_can_be_read_back_by_order_and_product(connection):
    warranty = warranty_repo.create(
        connection,
        order_id="order-001",
        product_id="laptop-002",
        coverage_months=24,
        purchase_date="2026-09-19",
    )
    assert warranty.warranty_id.startswith("warranty-")
    assert warranty_repo.get(connection, "order-001", "laptop-002") == warranty


def test_update_changes_coverage_and_purchase_date_together(connection):
    warranty = warranty_repo.update(
        connection, "warranty-002", coverage_months=48, purchase_date="2026-01-15"
    )
    assert warranty.coverage_months == 48
    assert warranty.purchase_date == "2026-01-15"


def test_update_leaves_the_field_that_was_not_given_alone(connection):
    before = warranty_repo.get_by_id(connection, "warranty-001")
    after = warranty_repo.update(connection, "warranty-001", coverage_months=6)
    assert after.coverage_months == 6
    assert after.purchase_date == before.purchase_date


def test_update_for_unknown_warranty_id_returns_none(connection):
    assert warranty_repo.update(connection, "does-not-exist", coverage_months=6) is None


def test_every_seeded_order_except_order_001_has_a_warranty(connection):
    covered = {warranty.order_id for warranty in warranty_repo.list_all(connection)}
    seeded_orders = {
        row[0] for row in connection.execute("SELECT order_id FROM orders")
    }
    assert seeded_orders - covered == {"order-001"}


def test_purchase_date_for_termination_leaves_a_past_purchase_alone():
    warranty = _unexpired("2023-01-01")
    assert (
        warranty_repo.purchase_date_for_termination(warranty, today=date(2026, 9, 19))
        == "2023-01-01"
    )


def test_purchase_date_for_termination_backdates_a_warranty_bought_today():
    warranty = _unexpired("2026-09-19")
    assert (
        warranty_repo.purchase_date_for_termination(warranty, today=date(2026, 9, 19))
        == "2026-09-18"
    )
