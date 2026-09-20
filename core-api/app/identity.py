"""Per-user isolation: the trusted subject arrives in a header and binds to one customer.

The identification number the customer types is an assertion, not a credential, so it can never
be the subject. The subject is whoever the chat frontend authenticated, delivered out of band in
X-End-User-Id and propagated by the workflow itself, never by the language model.
"""
import sqlite3
from dataclasses import dataclass

from fastapi import Depends, Header

from app.auth import OPERATOR, require_api_key
from app.config import get_settings
from app.errors import DomainError
from app.repositories import identity_bindings as bindings_repo

SUBJECT_HEADER = "X-End-User-Id"
ANONYMOUS_SUBJECT = "anonymous"


@dataclass(frozen=True)
class Subject:
    principal: str
    subject_id: str | None
    enforced: bool

    @property
    def is_operator(self) -> bool:
        return self.principal == OPERATOR

    def key(self) -> str:
        """Storage key for this subject's binding. With isolation on, a request that carries no
        end-user identity has no key at all and is refused rather than pooled into a shared one."""
        if self.subject_id:
            return self.subject_id
        if self.enforced:
            raise DomainError(
                status_code=403,
                code="identity_required",
                message=(
                    f"This request carries no {SUBJECT_HEADER} header, so it has no end-user "
                    "identity and cannot read or write customer data"
                ),
            )
        return ANONYMOUS_SUBJECT


def get_subject(
    principal: str = Depends(require_api_key),
    x_end_user_id: str | None = Header(default=None),
) -> Subject:
    settings = get_settings()
    return Subject(
        principal=principal,
        subject_id=(x_end_user_id or "").strip() or None,
        enforced=settings.isolation_enforced and principal != OPERATOR,
    )


def authorize_identification(
    connection: sqlite3.Connection, subject: Subject, client_id: str
) -> None:
    """Gate for the two endpoints where a customer states who they are. An unbound subject may
    claim any identification number; a bound one may only repeat its own."""
    if subject.is_operator:
        return
    bound = bindings_repo.get(connection, subject.key())
    if bound is None or bound == client_id:
        return
    if subject.enforced and not get_settings().rebinding_allowed:
        raise _mismatch()


def bind(connection: sqlite3.Connection, subject: Subject, client_id: str) -> None:
    """Record the link. Kept even with isolation off, so that turning it back on does not need
    every end user to identify again and so the derived-client endpoints still work."""
    if subject.is_operator:
        return
    bindings_repo.upsert(connection, subject.key(), client_id)


def authorize_client_access(
    connection: sqlite3.Connection, subject: Subject, client_id: str
) -> None:
    """Gate for every client-scoped read or write other than identification itself."""
    if subject.is_operator or not subject.enforced:
        return
    bound = bindings_repo.get(connection, subject.key())
    if bound is None:
        raise _not_verified()
    if bound != client_id:
        raise _mismatch()


def current_client_id(connection: sqlite3.Connection, subject: Subject) -> str | None:
    """The customer this subject acts as, derived rather than taken from the caller."""
    if subject.is_operator:
        return None
    bound = bindings_repo.get(connection, subject.key())
    if bound is None and subject.enforced:
        raise _not_verified()
    return bound


def bound_client_id(connection: sqlite3.Connection, subject: Subject) -> str | None:
    """Same lookup, but never refuses: for records that are worth stamping with a customer when
    one is known and are still legitimate when none is, such as an escalation."""
    if subject.is_operator or (subject.subject_id is None and subject.enforced):
        return None
    return bindings_repo.get(connection, subject.key())


def resolve_client_id(
    connection: sqlite3.Connection, subject: Subject, requested: str | None
) -> str:
    """With isolation on, the binding wins and a caller-supplied value may only agree with it."""
    bound = current_client_id(connection, subject)
    if subject.enforced:
        if requested is not None and requested != bound:
            raise _mismatch()
        return bound
    resolved = requested or bound
    if resolved is None:
        raise DomainError(
            status_code=400,
            code="client_id_required",
            message=(
                "With isolation disabled there is no trusted identity to derive the customer "
                "from, so client_id must be supplied"
            ),
        )
    return resolved


def _mismatch() -> DomainError:
    return DomainError(
        status_code=403,
        code="identity_mismatch",
        message="This end user is linked to a different customer and cannot access this one",
    )


def _not_verified() -> DomainError:
    return DomainError(
        status_code=403,
        code="identity_not_verified",
        message="This end user has not identified a customer yet in this store",
    )
