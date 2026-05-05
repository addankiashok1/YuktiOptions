import json
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    InsufficientBalanceError,
    InsufficientPositionError,
    PriceUnavailableError,
    WalletNotFoundError,
)
from app.core.redis import get_redis
from app.models.order import Order, OrderSide, OrderStatus
from app.models.position import Position
from app.models.wallet import Wallet
from app.models.wallet_transaction import TransactionType, WalletTransaction

_SCALE = Decimal("0.01")


class OrderService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── public entry point ────────────────────────────────────────────────────

    async def execute_order(
        self,
        user_id: uuid.UUID,
        symbol: str,
        side: str,
        quantity: int,
    ) -> Order:
        price = await self._get_price(symbol)
        order_value = (price * Decimal(quantity)).quantize(_SCALE)
        order_side = OrderSide(side)

        if order_side == OrderSide.BUY:
            return await self._buy(user_id, symbol, quantity, price, order_value)
        return await self._sell(user_id, symbol, quantity, price, order_value)

    # ── buy ───────────────────────────────────────────────────────────────────

    async def _buy(
        self,
        user_id: uuid.UUID,
        symbol: str,
        quantity: int,
        price: Decimal,
        order_value: Decimal,
    ) -> Order:
        # Lock order: wallet → position  (consistent across buy+sell → no deadlock)
        wallet = await self._lock_wallet(user_id)

        if wallet.balance < order_value:
            raise InsufficientBalanceError(
                f"Insufficient balance. Required ₹{order_value}, available ₹{wallet.balance}."
            )

        position = await self._lock_or_init_position(user_id, symbol)

        # Deduct wallet
        wallet.balance = (wallet.balance - order_value).quantize(_SCALE)

        # Weighted average price: preserves cost basis across multiple buys
        new_qty = position.quantity + quantity
        position.avg_price = (
            (position.avg_price * position.quantity + price * quantity) / new_qty
        ).quantize(_SCALE)
        position.quantity = new_qty

        order_id = uuid.uuid4()
        self.db.add(
            WalletTransaction(
                user_id=user_id,
                wallet_id=wallet.id,
                type=TransactionType.DEBIT,
                amount=order_value,
                balance_after=wallet.balance,
                reference_id=str(order_id),
            )
        )
        order = Order(
            id=order_id,
            user_id=user_id,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            price=price,
            order_value=order_value,
            status=OrderStatus.EXECUTED,
        )
        self.db.add(order)

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(order)
        return order

    # ── sell ──────────────────────────────────────────────────────────────────

    async def _sell(
        self,
        user_id: uuid.UUID,
        symbol: str,
        quantity: int,
        price: Decimal,
        order_value: Decimal,
    ) -> Order:
        # Lock order: wallet → position  (same ordering as buy → no deadlock)
        wallet = await self._lock_wallet(user_id)
        position = await self._lock_position(user_id, symbol)

        held = position.quantity if position else 0
        if held < quantity:
            raise InsufficientPositionError(
                f"Insufficient position in {symbol}. Held: {held}, requested: {quantity}."
            )

        # Reduce position (avg_price unchanged on partial sell — cost basis stays)
        position.quantity -= quantity

        # Credit wallet
        wallet.balance = (wallet.balance + order_value).quantize(_SCALE)

        order_id = uuid.uuid4()
        self.db.add(
            WalletTransaction(
                user_id=user_id,
                wallet_id=wallet.id,
                type=TransactionType.CREDIT,
                amount=order_value,
                balance_after=wallet.balance,
                reference_id=str(order_id),
            )
        )
        order = Order(
            id=order_id,
            user_id=user_id,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            price=price,
            order_value=order_value,
            status=OrderStatus.EXECUTED,
        )
        self.db.add(order)

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(order)
        return order

    # ── private helpers ───────────────────────────────────────────────────────

    async def _get_price(self, symbol: str) -> Decimal:
        redis = await get_redis()
        raw = await redis.get(f"price:{symbol}")
        if not raw:
            raise PriceUnavailableError(
                f"No live price for {symbol}. Ensure the market engine is running."
            )
        try:
            data = json.loads(raw)
            price = Decimal(str(data["price"])).quantize(_SCALE)
        except (json.JSONDecodeError, KeyError, Exception) as exc:
            raise PriceUnavailableError(f"Malformed price data for {symbol}.") from exc
        if price <= 0:
            raise PriceUnavailableError(f"Invalid price {price} for {symbol}.")
        return price

    async def _lock_wallet(self, user_id: uuid.UUID) -> Wallet:
        result = await self.db.execute(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update().limit(1)
        )
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise WalletNotFoundError("Wallet not found. Fund your account first.")
        return wallet

    async def _lock_position(self, user_id: uuid.UUID, symbol: str) -> Position | None:
        result = await self.db.execute(
            select(Position)
            .where(Position.user_id == user_id, Position.symbol == symbol)
            .with_for_update()
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _lock_or_init_position(self, user_id: uuid.UUID, symbol: str) -> Position:
        position = await self._lock_position(user_id, symbol)
        if position is None:
            # First buy for this symbol — create a zero-quantity placeholder.
            # The wallet lock already serializes concurrent buys from the same
            # user, so no two transactions can reach this branch simultaneously.
            position = Position(
                user_id=user_id,
                symbol=symbol,
                quantity=0,
                avg_price=Decimal("0"),
            )
            self.db.add(position)
            await self.db.flush()  # generate PK before referencing in buy logic
        return position
