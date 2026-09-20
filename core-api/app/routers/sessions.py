"""HTTP endpoints for the sessions domain."""
import sqlite3

from fastapi import APIRouter, Depends

from app.auth import require_api_key
from app.db import get_db
from app.repositories import sessions as sessions_repo
from app.schemas.sessions import Session, SessionUpdate

router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["sessions"],
    dependencies=[Depends(require_api_key)],
)


@router.get(
    "/{session_id}", response_model=Session, summary="Get a session's current memory"
)
def get_session(session_id: str, connection: sqlite3.Connection = Depends(get_db)) -> Session:
    return sessions_repo.get_or_create(connection, session_id)


@router.put(
    "/{session_id}", response_model=Session, summary="Save an explicit slot into a session"
)
def update_session(
    session_id: str,
    changes: SessionUpdate,
    connection: sqlite3.Connection = Depends(get_db),
) -> Session:
    return sessions_repo.update(connection, session_id, changes)
