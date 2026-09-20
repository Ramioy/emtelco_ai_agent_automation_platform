"""X-API-Key authentication. Two keys, two principals: the agent and the operator console."""
import hmac

from fastapi import Depends, Header, HTTPException, status

from app.config import get_settings
from app.errors import DomainError

AGENT = "agent"
OPERATOR = "operator"


def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """The agent key is matched first, so setting both keys to the same value degrades into a
    loud 403 on the operator endpoints instead of quietly promoting the agent."""
    settings = get_settings()
    if _matches(x_api_key, settings.tools_api_key):
        return AGENT
    if _matches(x_api_key, settings.operator_api_key):
        return OPERATOR
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
    )


def _matches(presented: str | None, expected: str) -> bool:
    return bool(presented) and hmac.compare_digest(presented, expected)


def require_operator_key(principal: str = Depends(require_api_key)) -> str:
    if principal != OPERATOR:
        raise DomainError(
            status_code=403,
            code="operator_only",
            message="This endpoint is reserved for the operations console",
        )
    return principal
