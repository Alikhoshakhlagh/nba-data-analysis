"""Nine-table star schema. Importing this package never creates a database."""

from .database import create_schema, create_sqlite_engine
from .schema import metadata

__all__ = ["create_schema", "create_sqlite_engine", "metadata"]
