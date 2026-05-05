from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

from sqlalchemy import func


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"      # limit / stop_limit: waiting for conditions
    TRIGGERED = "triggered"  # stop_limit: trigger hit, now acts as limit
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    side: Mapped[OrderSide] = mapped_column(
        SAEnum(OrderSide, name="order_side", create_constraint=True)
    )
    order_type: Mapped[OrderType] = mapped_column(
        SAEnum(OrderType, name="order_type", create_constraint=True),
        default=OrderType.MARKET,
    )
    quantity: Mapped[int] = mapped_column(Integer)

    # Execution fields — null until the order actually executes
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    order_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    # Limit / stop-limit fields
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    trigger_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)

    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status", create_constraint=True),
        default=OrderStatus.PENDING,
    )
    # created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    created_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    default=utc_now,
    server_default=func.now(),   # 🔥 THIS IS WHAT YOU ARE MISSING
    nullable=False
)
    __table_args__ = (
        # Matching engine scans this index on every price tick
        Index("ix_orders_symbol_status", "symbol", "status"),
    )
