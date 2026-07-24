"""Stub for the settings module."""
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str
    log_level: str


def load_settings(env: str) -> Settings:
    return Settings(database_url=f"sqlite:///{env}.db", log_level="INFO")
