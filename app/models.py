from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import re

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OrderStatus(StrEnum):
    ASSEMBLING = "Собирается"
    MISSING_ITEM = "Не хватает позиции"
    ASSEMBLED_FOR_COURIER = "Собран курьеру"
    ASSEMBLED_FOR_CDEK = "Собран на СДЭК"
    SELF_DELIVERY = "Везу сам заказ"
    THIRD_PARTY_COURIER = "Передан стороннему курьеру"
    DELIVERED = "Доставлен"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default=OrderStatus.ASSEMBLING.value)
    cdek_tracking_number: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    forwarded_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Telegram IDs can be greater than the maximum value of a 32-bit INTEGER.
    created_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
