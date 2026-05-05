import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_ALLOWED_SYMBOLS = {"NIFTY", "BANKNIFTY", "FINNIFTY"}


class OrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: int
    order_type: str = "market"
    limit_price: Decimal | None = None
    trigger_price: Decimal | None = None

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

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        lower = v.lower()
        if lower not in ("market", "limit", "stop_limit"):
            raise ValueError("order_type must be 'market', 'limit', or 'stop_limit'")
        return lower

    @field_validator("limit_price", "trigger_price")
    @classmethod
    def validate_price_positive(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("price must be positive")
        return v

    @model_validator(mode="after")
    def validate_type_requirements(self) -> "OrderRequest":
        if self.order_type == "limit":
            if self.limit_price is None:
                raise ValueError("limit_price is required for limit orders")
        if self.order_type == "stop_limit":
            if self.limit_price is None:
                raise ValueError("limit_price is required for stop_limit orders")
            if self.trigger_price is None:
                raise ValueError("trigger_price is required for stop_limit orders")
        return self


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    side: str
    order_type: str
    quantity: int
    status: str
    price: Decimal | None = None
    order_value: Decimal | None = None
    limit_price: Decimal | None = None
    trigger_price: Decimal | None = None
    created_at: datetime
