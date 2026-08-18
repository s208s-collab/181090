from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_ids(value: str | None) -> frozenset[int]:
    if not value or not value.strip():
        return frozenset()
    try:
        return frozenset(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise ValueError("ALLOWED_TELEGRAM_IDS должен содержать Telegram ID через запятую") from error


@dataclass(frozen=True)
class Settings:
    bot_token: str
    webapp_url: str
    database_url: str
    allowed_telegram_ids: frozenset[int]
    mini_app_auth_max_age: int
    dev_mode: bool

    @property
    def database_url_sqlalchemy(self) -> str:
        """Приводит распространённые Postgres URL к драйверу psycopg 3."""
        if self.database_url.startswith("postgres://"):
            return "postgresql+psycopg://" + self.database_url.removeprefix("postgres://")
        if self.database_url.startswith("postgresql://"):
            return "postgresql+psycopg://" + self.database_url.removeprefix("postgresql://")
        return self.database_url

    def validate_for_runtime(self) -> None:
        if not self.bot_token:
            raise RuntimeError("Не задан BOT_TOKEN. Скопируйте .env.example в .env и заполните токен.")
        if not self.webapp_url.startswith("https://"):
            raise RuntimeError("WEBAPP_URL должен быть публичным HTTPS-адресом Mini App.")


settings = Settings(
    bot_token=os.getenv("BOT_TOKEN", "").strip(),
    webapp_url=os.getenv("WEBAPP_URL", "").rstrip("/"),
    database_url=os.getenv("DATABASE_URL", "sqlite:///./orders.db").strip(),
    allowed_telegram_ids=_as_ids(os.getenv("ALLOWED_TELEGRAM_IDS")),
    mini_app_auth_max_age=int(os.getenv("MINI_APP_AUTH_MAX_AGE", "86400")),
    dev_mode=_as_bool(os.getenv("DEV_MODE")),
)

