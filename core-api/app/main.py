"""FastAPI application entrypoint; business routers are registered here."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import get_settings
from app.db import init_db
from app.errors import register_exception_handlers
from app.routers.catalog import router as catalog_router
from app.routers.clients import router as clients_router
from app.routers.escalations import router as escalations_router
from app.routers.orders import router as orders_router
from app.routers.sessions import router as sessions_router
from app.routers.warranty import router as warranty_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(get_settings().database_path)
    yield


OPENAPI_TAGS = [
    {
        "name": "clients",
        "description": "Client identification and registration. Identification, not "
        "authentication -- there is no password or credential involved.",
    },
    {
        "name": "catalog",
        "description": "Product browsing and comparison for consultative sales.",
    },
    {
        "name": "orders",
        "description": "Order status, delivery tracking, and simulated purchases.",
    },
    {
        "name": "warranty",
        "description": "Warranty coverage checks and claim filing, with automatic "
        "safety escalation.",
    },
    {
        "name": "sessions",
        "description": "Current and cross-session conversational memory.",
    },
    {
        "name": "escalations",
        "description": "Manual escalation of a case to a human agent.",
    },
]

app = FastAPI(title="Agent Tools API", lifespan=lifespan, openapi_tags=OPENAPI_TAGS)
register_exception_handlers(app)
app.include_router(catalog_router)
app.include_router(clients_router)
app.include_router(escalations_router)
app.include_router(orders_router)
app.include_router(sessions_router)
app.include_router(warranty_router)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
