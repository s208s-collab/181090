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
    """Безопасно добавляет новые поля и обновляет старые статусы."""
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            columns = ("created_by_telegram_id", "updated_by_telegram_id")
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
            connection.execute(
                text(
                    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS "
                    "cdek_tracking_number VARCHAR(128) NOT NULL DEFAULT ''"
                )
            )
        elif engine.dialect.name == "sqlite":
            columns = {
                row["name"]
                for row in connection.execute(text("PRAGMA table_info(orders)")).mappings()
            }
            if "cdek_tracking_number" not in columns:
                connection.execute(
                    text("ALTER TABLE orders ADD COLUMN cdek_tracking_number VARCHAR(128) NOT NULL DEFAULT ''")
                )

        connection.execute(
            text(
                """
                UPDATE orders
                SET status = CASE status
                    WHEN 'Новый' THEN 'Собирается'
                    WHEN 'На сборку' THEN 'Собирается'
                    WHEN 'Собран' THEN 'Собран курьеру'
                    WHEN 'Передан в доставку' THEN 'Передан стороннему курьеру'
                    WHEN 'Отправлен СДЭК' THEN 'Собран на СДЭК'
                    WHEN 'Передан курьеру' THEN 'Передан стороннему курьеру'
                    ELSE status
                END
                WHERE status IN (
                    'Новый', 'На сборку', 'Собран', 'Передан в доставку',
                    'Отправлен СДЭК', 'Передан курьеру'
                )
                """
            )
        )


def get_session():
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
