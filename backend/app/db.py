"""
Database setup (SQLAlchemy + SQLite).

- `Base` is the parent class for all tables (see models.py).
- Each app instance gets its own engine/session factory on `app.state`,
  so tests can use a separate temporary database.
- Tables are created automatically at startup (`create_all`). That is fine for
  this prototype; see backend/README.md for how to reset or migrate later.
"""

import logging
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

log = logging.getLogger("mendora.db")


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    engine = create_engine(
        database_url,
        # FastAPI runs requests on several threads; SQLite needs this to allow that.
        # check_same_thread: FastAPI uses several threads. timeout: wait (instead of failing) if another
        # request is writing at the same moment — e.g. two simultaneous booking attempts.
        connect_args={"check_same_thread": False, "timeout": 15} if is_sqlite else {},
    )
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")  # enforce relationships
            cursor.execute("PRAGMA journal_mode=WAL")  # better concurrent reads
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_tables(engine: Engine) -> None:
    from . import models  # noqa: F401  (registers the tables on Base.metadata)

    Base.metadata.create_all(engine)
    upgrade_schema(engine)


def upgrade_schema(engine: Engine) -> None:
    """
    Tiny automatic migration: adds any NEW, NULLABLE columns that an older database file is missing
    (e.g. the safety columns added in Step 6), so existing data keeps working. Nothing is deleted.
    Anything more complex (renames, new required columns) needs a real migration tool such as Alembic.
    """
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            if not column.nullable or column.primary_key:
                raise RuntimeError(
                    f"Database column {table.name}.{column.name} is missing and can't be added automatically. "
                    "Delete mendora.db to start fresh (prototype) or add a migration."
                )
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column.type.compile(engine.dialect)}'
            with engine.begin() as conn:
                conn.execute(text(ddl))
            log.info("Database upgraded: added column %s.%s", table.name, column.name)


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one database session per HTTP request, always closed afterwards."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
