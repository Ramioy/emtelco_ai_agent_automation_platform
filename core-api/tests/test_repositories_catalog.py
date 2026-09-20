"""Tests for the catalog SQL repository, against a temporary SQLite database."""
import pytest

from app.db import init_db
from app.repositories import catalog as catalog_repo
from app.schemas.catalog import Product


@pytest.fixture
def connection(tmp_path):
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


def test_init_db_seeds_products_from_fixture(connection):
    count = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert count > 0


def test_seed_is_idempotent(connection):
    before = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    catalog_repo.seed(connection)
    after = connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    assert before == after


def test_list_products_with_no_filters_returns_all(connection):
    products = catalog_repo.list_products(connection)
    assert len(products) == connection.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]


def test_list_products_filters_by_category(connection):
    products = catalog_repo.list_products(connection, category="laptop")
    assert len(products) == 3
    assert all(product.category == "laptop" for product in products)


def test_list_products_filters_by_max_budget(connection):
    products = catalog_repo.list_products(connection, max_budget=2000000)
    assert {product.id for product in products} == {"tablet-001", "headphones-001", "headphones-002"}


def test_list_products_filters_by_category_and_max_budget(connection):
    products = catalog_repo.list_products(connection, category="laptop", max_budget=5000000)
    assert {product.id for product in products} == {"laptop-001", "laptop-002"}


def test_list_products_unknown_category_returns_empty(connection):
    assert catalog_repo.list_products(connection, category="drone") == []


def test_list_products_returns_parsed_specs_and_fields(connection):
    products = catalog_repo.list_products(connection, category="tablet")
    assert len(products) == 1
    product = products[0]
    assert product.id == "tablet-001"
    assert product.name == "TabPro 11"
    assert product.brand == "Northgate"
    assert product.price == 1800000
    assert product.stock == 12
    assert product.specs == {"ram_gb": 6, "storage_gb": 128, "screen_inches": 11}


def test_get_by_ids_returns_only_matching_products(connection):
    products = catalog_repo.get_by_ids(connection, ["laptop-001", "does-not-exist"])
    assert {product.id for product in products} == {"laptop-001"}


def test_get_by_ids_with_empty_list_returns_empty(connection):
    assert catalog_repo.get_by_ids(connection, []) == []


def test_compute_key_differences_flags_differing_top_level_and_spec_fields():
    product_a = Product(
        id="a", category="laptop", name="A", brand="Zenda",
        price=100, specs={"ram_gb": 8, "cpu": "i5"}, stock=1,
    )
    product_b = Product(
        id="b", category="laptop", name="B", brand="Zenda",
        price=200, specs={"ram_gb": 8, "cpu": "i7"}, stock=1,
    )

    differences = catalog_repo.compute_key_differences([product_a, product_b])

    assert set(differences) == {"price", "specs.cpu"}
    assert "brand" not in differences
    assert "category" not in differences
    assert "stock" not in differences
    assert "specs.ram_gb" not in differences


def test_compute_key_differences_flags_specs_present_in_only_one_product():
    product_a = Product(
        id="a", category="laptop", name="A", brand="Zenda",
        price=100, specs={"gpu": "RTX 3050"}, stock=1,
    )
    product_b = Product(
        id="b", category="smartphone", name="B", brand="Halox",
        price=100, specs={"camera_mp": 48}, stock=1,
    )

    differences = catalog_repo.compute_key_differences([product_a, product_b])

    assert set(differences) == {"category", "brand", "specs.gpu", "specs.camera_mp"}


def test_compute_key_differences_over_identical_products_is_empty():
    product = Product(
        id="a", category="laptop", name="A", brand="Zenda",
        price=100, specs={"ram_gb": 8}, stock=1,
    )
    identical_copy = product.model_copy(update={"id": "b"})

    assert catalog_repo.compute_key_differences([product, identical_copy]) == []


def test_decrement_stock_reduces_stock_by_one(connection):
    before = catalog_repo.get_by_ids(connection, ["laptop-001"])[0].stock
    catalog_repo.decrement_stock(connection, "laptop-001")
    after = catalog_repo.get_by_ids(connection, ["laptop-001"])[0].stock
    assert after == before - 1


def test_decrement_stock_can_reach_zero(connection):
    catalog_repo.decrement_stock(connection, "laptop-003")  # seeded with stock=3
    catalog_repo.decrement_stock(connection, "laptop-003")
    catalog_repo.decrement_stock(connection, "laptop-003")
    product = catalog_repo.get_by_ids(connection, ["laptop-003"])[0]
    assert product.stock == 0
