"""Environment-based configuration; the identity settings decide whether isolation is real."""
import os
from dataclasses import dataclass

ISOLATION_ENFORCED = "enforced"
ISOLATION_DISABLED = "disabled"
REBINDING_DENIED = "denied"
REBINDING_ALLOWED = "allowed"


@dataclass(frozen=True)
class Settings:
    database_path: str
    tools_api_key: str
    operator_api_key: str
    identity_isolation: str
    identity_rebinding: str

    @property
    def isolation_enforced(self) -> bool:
        # Anything other than the one spelling that turns it off leaves it on: a typo in the
        # environment file must not silently open the boundary.
        return self.identity_isolation != ISOLATION_DISABLED

    @property
    def rebinding_allowed(self) -> bool:
        return self.identity_rebinding == REBINDING_ALLOWED


def get_settings() -> Settings:
    return Settings(
        database_path=os.environ.get("DATABASE_PATH", "./app/data/db/mock.db"),
        tools_api_key=os.environ.get("TOOLS_API_KEY", "change-me"),
        operator_api_key=os.environ.get("OPERATOR_API_KEY", "change-me-operator"),
        identity_isolation=os.environ.get("IDENTITY_ISOLATION", ISOLATION_ENFORCED),
        identity_rebinding=os.environ.get("IDENTITY_REBINDING", REBINDING_DENIED),
    )
