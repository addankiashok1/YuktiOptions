from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.wallet import Wallet


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TransactionType(str, enum.Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wallets.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="transaction_type", create_constraint=True)
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2))
    reference_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    wallet: Mapped[Wallet] = relationship(back_populates="transactions")
