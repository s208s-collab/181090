from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import OrderStatus


class OrderUpdate(BaseModel):
    status: OrderStatus | None = None
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def has_a_change(self):
        if self.status is None and self.comment is None:
            raise ValueError("Передайте статус или комментарий")
        return self


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    message_text: str
    comment: str
    status: OrderStatus
    forwarded_from: str | None
    created_by_name: str | None
    updated_by_name: str | None
    created_at: datetime
    updated_at: datetime
