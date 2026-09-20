"""HTTP endpoints for the clients domain."""
import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import require_api_key
from app.db import get_db
from app.errors import DomainError
from app.repositories import client_memory as client_memory_repo
from app.repositories import clients as clients_repo
from app.repositories import interactions as interactions_repo
from app.repositories import sessions as sessions_repo
from app.schemas.clients import Client, ClientCreate

router = APIRouter(
    prefix="/api/v1/clients",
    tags=["clients"],
    dependencies=[Depends(require_api_key)],
)


class ClientCreateResponse(BaseModel):
    client: Client


@router.get("/{client_id}", summary="Check whether a client is already registered")
def get_client(
    client_id: str,
    session_id: str | None = None,
    connection: sqlite3.Connection = Depends(get_db),
):
    client = clients_repo.get(connection, client_id)
    if client is None:
        return JSONResponse(status_code=404, content={"exists": False})

    if session_id is not None:
        sessions_repo.link_client(connection, session_id, client_id)

    previous_memory = client_memory_repo.get(connection, client_id)
    return {
        "exists": True,
        "client": client.model_dump(),
        "previous_memory": previous_memory.model_dump() if previous_memory else None,
    }


@router.post(
    "", response_model=ClientCreateResponse, status_code=201, summary="Register a new client"
)
def create_client(
    payload: ClientCreate,
    session_id: str | None = None,
    connection: sqlite3.Connection = Depends(get_db),
) -> ClientCreateResponse:
    if clients_repo.exists(connection, payload.client_id):
        raise DomainError(
            status_code=409, code="already_exists", message="Client already exists"
        )
    client = clients_repo.insert(connection, payload)

    if session_id is not None:
        sessions_repo.link_client(connection, session_id, client.client_id)

    return ClientCreateResponse(client=client)


@router.get(
    "/{client_id}/history", summary="Get a client's current memory and past session summaries"
)
def get_client_history(client_id: str, connection: sqlite3.Connection = Depends(get_db)):
    current_memory = client_memory_repo.get(connection, client_id)
    past_sessions = interactions_repo.list_sessions_for_client(connection, client_id)
    return {
        "current_memory": current_memory.model_dump() if current_memory else None,
        "past_sessions": past_sessions,
    }
