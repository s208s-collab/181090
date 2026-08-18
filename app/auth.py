from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, status

from app.config import settings


@dataclass(frozen=True)
class MiniAppUser:
    telegram_id: int
    name: str
    username: str | None = None


def validate_init_data(init_data: str) -> MiniAppUser:
    """Проверяет подпись initData по алгоритму Telegram Mini Apps."""
    if not settings.bot_token:
        raise ValueError("BOT_TOKEN не задан")

    pairs = parse_qsl(init_data, keep_blank_values=True)
    values = dict(pairs)
    received_hash = values.pop("hash", None)
    if not received_hash:
        raise ValueError("В initData отсутствует hash")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Подпись Telegram не прошла проверку")

    try:
        auth_date = int(values["auth_date"])
        raw_user = json.loads(values["user"])
        telegram_id = int(raw_user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Некорректные данные запуска Telegram") from error

    if time.time() - auth_date > settings.mini_app_auth_max_age:
        raise ValueError("Срок действия запуска Mini App истёк — откройте её заново из бота")
    if auth_date > time.time() + 300:
        raise ValueError("Некорректное время запуска Mini App")
    if settings.allowed_telegram_ids and telegram_id not in settings.allowed_telegram_ids:
        raise PermissionError("Для этого Telegram-аккаунта нет доступа к заказам")

    full_name = " ".join(filter(None, [raw_user.get("first_name"), raw_user.get("last_name")])).strip()
    return MiniAppUser(
        telegram_id=telegram_id,
        name=full_name or raw_user.get("username") or f"Пользователь {telegram_id}",
        username=raw_user.get("username"),
    )


async def require_mini_app_user(
    x_telegram_init_data: str | None = Header(default=None),
    x_dev_user_id: str | None = Header(default=None),
    x_dev_user_name: str | None = Header(default=None),
) -> MiniAppUser:
    """Зависимость FastAPI: разрешает только верифицированный запуск внутри Telegram."""
    if settings.dev_mode and x_dev_user_id:
        try:
            return MiniAppUser(telegram_id=int(x_dev_user_id), name=x_dev_user_name or "Тестовый пользователь")
        except ValueError:
            pass

    if not x_telegram_init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Откройте заказы внутри Telegram")
    try:
        return validate_init_data(x_telegram_init_data)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error

