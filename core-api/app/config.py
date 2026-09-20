"""Environment-based configuration; no settings library, only two variables so far."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_path: str
    tools_api_key: str


def get_settings() -> Settings:
    return Settings(
        database_path=os.environ.get("DATABASE_PATH", "./app/data/mock.db"),
        tools_api_key=os.environ.get("TOOLS_API_KEY", "change-me"),
    )
