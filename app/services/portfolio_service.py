import json
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.models.position import Position
from app.schemas.portfolio import PortfolioResponse, PositionPnLResponse

_ZERO = Decimal("0")
_SCALE = Decimal("0.01")
_PCT_SCALE = Decimal("0.01")


class PortfolioService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_portfolio(self, user_id: uuid.UUID) -> PortfolioResponse:
        result = await self.db.execute(
            select(Position)
            .where(Position.user_id == user_id, Position.quantity > 0)
            .order_by(Position.symbol)
        )
        positions = result.scalars().all()

        redis = await get_redis()
        enriched: list[PositionPnLResponse] = []
        total_invested = _ZERO
        total_current_value = _ZERO

        for pos in positions:
            invested = (pos.avg_price * pos.quantity).quantize(_SCALE)
            total_invested += invested

            current_price = await self._fetch_price(redis, pos.symbol, fallback=pos.avg_price)
            current_value = (current_price * pos.quantity).quantize(_SCALE)
            total_current_value += current_value

            pnl = (current_value - invested).quantize(_SCALE)
            pnl_pct = (pnl / invested * 100).quantize(_PCT_SCALE) if invested else _ZERO

            enriched.append(
                PositionPnLResponse(
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    avg_price=pos.avg_price,
                    current_price=current_price,
                    invested=invested,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                )
            )

        total_pnl = (total_current_value - total_invested).quantize(_SCALE)
        total_pnl_pct = (
            (total_pnl / total_invested * 100).quantize(_PCT_SCALE)
            if total_invested
            else _ZERO
        )

        return PortfolioResponse(
            positions=enriched,
            total_invested=total_invested,
            portfolio_value=total_current_value,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
        )

    @staticmethod
    async def _fetch_price(redis, symbol: str, fallback: Decimal) -> Decimal:
        try:
            raw = await redis.get(f"price:{symbol}")
            if not raw:
                return fallback
            data = json.loads(raw)
            return Decimal(str(data["price"])).quantize(_SCALE)
        except (json.JSONDecodeError, KeyError, Exception):
            return fallback
