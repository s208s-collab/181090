from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import MiniAppUser, require_mini_app_user
from app.bot import prepare_bot, run_bot
from app.config import settings
from app.database import Base, engine, get_session, upgrade_schema
from app.models import Order
from app.schemas import OrderOut, OrderUpdate


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC_DIR = Path(__file__).resolve().parent / "static"


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings.validate_for_runtime()
    Base.metadata.create_all(bind=engine)
    upgrade_schema()
    # Проверяем токен и URL кнопки до того, как сервис станет доступен.
    bot, dispatcher = await prepare_bot()
    bot_task = asyncio.create_task(run_bot(bot, dispatcher), name="telegram-bot-polling")
    try:
        yield
    finally:
        bot_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await bot_task
        engine.dispose()


app = FastAPI(title="Печной двор — Заказы", lifespan=lifespan)


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/orders", response_model=list[OrderOut], tags=["orders"])
async def list_orders(
    _: Annotated[MiniAppUser, Depends(require_mini_app_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[Order]:
    return list(session.scalars(select(Order).order_by(Order.created_at.desc(), Order.id.desc())))


@app.patch("/api/orders/{order_id}", response_model=OrderOut, tags=["orders"])
async def update_order(
    order_id: int,
    update: OrderUpdate,
    user: Annotated[MiniAppUser, Depends(require_mini_app_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Order:
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")

    if update.status is not None:
        order.status = update.status.value
    if update.comment is not None:
        order.comment = update.comment.strip()
    order.updated_by_telegram_id = user.telegram_id
    order.updated_by_name = user.name
    session.commit()
    session.refresh(order)
    return order


@app.delete("/api/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["orders"])
async def delete_order(
    order_id: int,
    _: Annotated[MiniAppUser, Depends(require_mini_app_user)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заказ не найден")

    session.delete(order)
    session.commit()


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
