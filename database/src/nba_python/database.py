"""Explicit STRICT schema creation and per-connection foreign-key enforcement."""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url

from .schema import metadata


def require_strict_support(version):
    if tuple(int(part) for part in version.split(".")[:3]) < (3, 37, 0):
        raise RuntimeError(f"SQLite {version} is too old; STRICT requires SQLite 3.37.0+.")


def _configure_connection(dbapi_connection, _record):
    has_autocommit = hasattr(dbapi_connection, "autocommit")
    if has_autocommit:
        previous = dbapi_connection.autocommit
        dbapi_connection.autocommit = True
    cursor = dbapi_connection.cursor()
    try:
        require_strict_support(cursor.execute("SELECT sqlite_version()").fetchone()[0])
        cursor.execute("PRAGMA foreign_keys=ON")
        if cursor.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("Foreign keys could not be enabled.")
    finally:
        cursor.close()
        if has_autocommit:
            dbapi_connection.autocommit = previous


def create_sqlite_engine(url="sqlite+pysqlite:///:memory:"):
    if make_url(url).get_backend_name() != "sqlite":
        raise ValueError("Only SQLite is supported.")
    engine = create_engine(url)
    event.listen(engine, "connect", _configure_connection)
    return engine


def create_schema(engine):
    """Create nine empty tables. This is not an existing-schema migration."""
    with engine.begin() as connection:
        require_strict_support(connection.exec_driver_sql("SELECT sqlite_version()").scalar_one())
        if connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
            raise RuntimeError("Foreign keys are OFF; use create_sqlite_engine().")
        metadata.create_all(connection)
