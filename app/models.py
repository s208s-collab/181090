from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import re

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OrderStatus(StrEnum):
    NEW = "Новый"
    ASSEMBLY_QUEUE = "На сборку"
    ASSEMBLING = "Собирается"
    MISSING_ITEM = "Не хватает позиции"
    ASSEMBLED = "Собран"
    HANDED_TO_DELIVERY = "Передан в доставку"
    SENT_CDEK = "Отправлен СДЭК"
    HANDED_TO_COURIER = "Передан курьеру"
    DELIVERED = "Доставлен"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default=OrderStatus.NEW.value)
    forwarded_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def order_number(self) -> str:
        """Номер, который указан в пересланном сообщении клиента."""
        match = re.search(r"(?m)^\s*(?:№\s*)?(\d{1,12})\s*(?:[)\].:—–-]|$)", self.message_text)
        return match.group(1) if match else str(self.id)
