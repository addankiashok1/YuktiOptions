from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderSide, OrderStatus, OrderType
from app.schemas.orderbook import OrderBookResponse, PriceLevel


class OrderBookService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_order_book(self, symbol: str) -> OrderBookResponse:
        result = await self.db.execute(
            select(Order.side, Order.limit_price, Order.quantity).where(
                Order.symbol == symbol,
                Order.order_type == OrderType.LIMIT,
                Order.status == OrderStatus.PENDING,
                Order.limit_price.isnot(None),
            )
        )
        rows = result.all()

        bids: dict[Decimal, int] = defaultdict(int)
        asks: dict[Decimal, int] = defaultdict(int)

        for side, limit_price, quantity in rows:
            if side == OrderSide.BUY:
                bids[limit_price] += quantity
            else:
                asks[limit_price] += quantity

        return OrderBookResponse(
            symbol=symbol,
            bids=[
                PriceLevel(price=p, quantity=q)
                for p, q in sorted(bids.items(), reverse=True)  # highest bid first
            ],
            asks=[
                PriceLevel(price=p, quantity=q)
                for p, q in sorted(asks.items())  # lowest ask first
            ],
        )
