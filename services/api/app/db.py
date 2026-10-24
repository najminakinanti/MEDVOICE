from functools import lru_cache

from sqlalchemy import create_engine

from .config import get_settings


@lru_cache
def engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)


def get_conn():
    """Dependency FastAPI: satu transaksi per request (commit bila sukses, rollback bila error)."""
    with engine().begin() as conn:
        yield conn
