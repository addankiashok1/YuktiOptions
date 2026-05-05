from decimal import Decimal

from pydantic import BaseModel


class PriceLevel(BaseModel):
    price: Decimal
    quantity: int


class OrderBookResponse(BaseModel):
    symbol: str
    bids: list[PriceLevel]  # BUY orders — highest price first
    asks: list[PriceLevel]  # SELL orders — lowest price first
