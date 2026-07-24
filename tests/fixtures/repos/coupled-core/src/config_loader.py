"""config_loader.py — tightly coupled to project internals.

This file imports from 3 internal modules, so it should be flagged as
skipped (tightly coupled), not flagged as extractable.
"""
from .database import get_connection
from .logger import get_logger
from .settings import load_settings


def load_config(env: str = "dev"):
    """Load configuration from environment."""
    settings = load_settings(env)
    db = get_connection(settings.database_url)
    log = get_logger(settings.log_level)
    return {"db": db, "log": log, "settings": settings}
