from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    quantity: int
    avg_price: Decimal
    stop_loss: Decimal | None = None
    target_price: Decimal | None = None


class PositionListResponse(BaseModel):
    positions: list[PositionResponse]


class UpdateSLRequest(BaseModel):
    symbol: str
    stop_loss: Decimal | None = None
    target_price: Decimal | None = None

    @field_validator("stop_loss", "target_price")
    @classmethod
    def must_be_positive(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("Price must be positive.")
        return v

    def model_post_init(self, __context) -> None:
        if (
            self.stop_loss is not None
            and self.target_price is not None
            and self.stop_loss >= self.target_price
        ):
            raise ValueError("stop_loss must be less than target_price.")


class UpdateSLResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    stop_loss: Decimal | None
    target_price: Decimal | None
