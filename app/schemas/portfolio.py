from decimal import Decimal

from pydantic import BaseModel


class PositionPnLResponse(BaseModel):
    symbol: str
    quantity: int
    avg_price: Decimal
    current_price: Decimal
    invested: Decimal
    pnl: Decimal
    pnl_pct: Decimal


class PortfolioResponse(BaseModel):
    positions: list[PositionPnLResponse]
    total_invested: Decimal
    portfolio_value: Decimal
    total_pnl: Decimal
    total_pnl_pct: Decimal
