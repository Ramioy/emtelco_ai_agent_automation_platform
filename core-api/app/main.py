"""FastAPI application entrypoint; business routers are registered here."""
import logging
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


logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.database_path)
    if not settings.isolation_enforced:
        logger.warning(
            "IDENTITY_ISOLATION=%s: per-user isolation is OFF. Any caller can read and write "
            "any customer's data. Do not run a shipped configuration like this.",
            settings.identity_isolation,
        )
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
        "description": "Support tickets: raised by the agent or by the automatic safety "
        "escalation, then worked through their lifecycle from the operations console.",
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
    identity_isolation: str
    identity_rebinding: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """The identity fields are part of the answer on purpose: which mode is active has to be
    readable from the running service, not only from the environment file."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        identity_isolation=settings.identity_isolation,
        identity_rebinding=settings.identity_rebinding,
    )
