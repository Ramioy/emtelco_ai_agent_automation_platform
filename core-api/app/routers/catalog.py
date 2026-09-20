"""HTTP endpoints for the catalog domain."""
import sqlite3

from fastapi import APIRouter, Depends

from app.auth import require_api_key
from app.db import get_db
from app.errors import DomainError
from app.repositories import catalog as catalog_repo
from app.repositories import sessions as sessions_repo
from app.schemas.catalog import CompareRequest, CompareResponse, Product

router = APIRouter(
    prefix="/api/v1/catalog",
    tags=["catalog"],
    dependencies=[Depends(require_api_key)],
)


@router.get(
    "/products",
    response_model=list[Product],
    summary="List products, optionally filtered by category and budget",
)
def get_products(
    category: str | None = None,
    max_budget: int | None = None,
    session_id: str | None = None,
    connection: sqlite3.Connection = Depends(get_db),
) -> list[Product]:
    """session_id is optional: when given, every returned product id is recorded in that
    session's products_viewed as a side effect."""
    products = catalog_repo.list_products(connection, category=category, max_budget=max_budget)
    if session_id is not None and products:
        sessions_repo.record_products_viewed(
            connection, session_id, [product.id for product in products]
        )
    return products


@router.post(
    "/compare", response_model=CompareResponse, summary="Compare two or more products by id"
)
def compare_products(
    payload: CompareRequest,
    connection: sqlite3.Connection = Depends(get_db),
) -> CompareResponse:
    found = {product.id: product for product in catalog_repo.get_by_ids(connection, payload.ids)}
    missing_ids = [product_id for product_id in payload.ids if product_id not in found]
    if missing_ids:
        raise DomainError(
            status_code=404,
            code="not_found",
            message=f"Products not found: {', '.join(missing_ids)}",
        )

    products = [found[product_id] for product_id in payload.ids]
    return CompareResponse(
        products=products,
        key_differences=catalog_repo.compute_key_differences(products),
    )
