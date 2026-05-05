from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    quantity: int
    avg_price: Decimal


class PositionListResponse(BaseModel):
    positions: list[PositionResponse]
