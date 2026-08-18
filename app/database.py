from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine_options: dict = {"pool_pre_ping": True}
if settings.database_url_sqlalchemy.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.database_url_sqlalchemy, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def upgrade_schema() -> None:
    """Обновляет ранние версии таблицы без ручной работы в Railway.

    У Telegram ID нет ограничения в 32 бита, поэтому в PostgreSQL для них
    нужен BIGINT. SQLite не требует отдельного изменения типа.
    """
    if engine.dialect.name != "postgresql":
        return

    columns = ("created_by_telegram_id", "updated_by_telegram_id")
    with engine.begin() as connection:
        integer_columns = set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'orders' "
                    "AND data_type = 'integer'"
                )
            ).scalars()
        )
        for column in columns:
            if column in integer_columns:
                connection.execute(text(f"ALTER TABLE orders ALTER COLUMN {column} TYPE BIGINT"))


def get_session():
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
