"""HTTP endpoints for the sessions domain."""
import sqlite3

from fastapi import APIRouter, Depends

from app import identity
from app.auth import require_api_key
from app.db import get_db
from app.identity import Subject, get_subject
from app.repositories import sessions as sessions_repo
from app.schemas.sessions import Session, SessionUpdate

router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["sessions"],
    dependencies=[Depends(require_api_key)],
)


def _authorize(connection: sqlite3.Connection, subject: Subject, session: Session) -> Session:
    """Session rows start out anonymous scratch state, so there is nothing to protect until one
    is linked to a customer. Once it is, it carries that customer's name, budgets and last order
    and is read and written by the end user bound to them, and nobody else. The workflow never
    lets the model choose a session id, but the boundary must not depend on that."""
    if session.client_id is not None:
        identity.authorize_client_access(connection, subject, session.client_id)
    return session


@router.get(
    "/{session_id}", response_model=Session, summary="Get a session's current memory"
)
def get_session(
    session_id: str,
    connection: sqlite3.Connection = Depends(get_db),
    subject: Subject = Depends(get_subject),
) -> Session:
    return _authorize(connection, subject, sessions_repo.get_or_create(connection, session_id))


@router.put(
    "/{session_id}", response_model=Session, summary="Save an explicit slot into a session"
)
def update_session(
    session_id: str,
    changes: SessionUpdate,
    connection: sqlite3.Connection = Depends(get_db),
    subject: Subject = Depends(get_subject),
) -> Session:
    _authorize(connection, subject, sessions_repo.get_or_create(connection, session_id))
    return sessions_repo.update(connection, session_id, changes)
