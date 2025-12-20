# backend/app/db_init.py
from .migrations import run_migrations, ensure_default_user


def init_db() -> int:
    """
    Run idempotent migrations and return the default user id.
    """
    return run_migrations()


def get_default_user_id() -> int:
    """
    Convenience helper for callers that need the local user id
    without rerunning migrations.
    """
    return ensure_default_user()
