import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

_ALLOWED_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY"}


class OrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: int

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _ALLOWED_SYMBOLS:
            raise ValueError(f"symbol must be one of: {sorted(_ALLOWED_SYMBOLS)}")
        return upper

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        lower = v.lower()
        if lower not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        return lower

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("quantity must be greater than 0")
        return v


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    side: str
    quantity: int
    price: Decimal
    order_value: Decimal
    status: str
    created_at: datetime
