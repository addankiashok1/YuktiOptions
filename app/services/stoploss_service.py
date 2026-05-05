"""
Stop-loss / target background engine.

Subscribes to Redis "market_data" and automatically executes a full SELL when:
  - current_price <= position.stop_loss     (stop-loss hit)
  - current_price >= position.target_price  (target hit)

Deadlock safety
---------------
Lock ordering is always:  wallet → position
This matches OrderService and prevents any cycle with concurrent user orders.

Duplicate-execution safety
--------------------------
After acquiring the position lock, SL/Target fields are cleared (set NULL) and
flushed within the same transaction BEFORE the sell executes.  Any concurrent
check that arrives after the flush will see NULL and skip the position.
"""

import asyncio
import json
import logging
import uuid
from decimal import Decimal

from sqlalchemy import and_, or_, select

from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis
from app.models.order import Order, OrderSide, OrderStatus
from app.models.position import Position
from app.models.wallet import Wallet
from app.models.wallet_transaction import TransactionType, WalletTransaction

log = logging.getLogger(__name__)

_CHANNEL = "market_data"
_SCALE = Decimal("0.01")


class StopLossService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="stoploss-engine")
            log.info("Stop-loss engine started.")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    # ── main loop ─────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    tick = json.loads(message["data"])
                    symbol: str = tick["symbol"]
                    price = Decimal(str(tick["price"])).quantize(_SCALE)
                except Exception:
                    continue
                await self._check_symbol(symbol, price)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.exception("Stop-loss engine crashed: %s", exc)
        finally:
            await pubsub.unsubscribe(_CHANNEL)
            await pubsub.aclose()
            log.info("Stop-loss engine stopped.")

    # ── scan + execute ────────────────────────────────────────────────────────

    async def _check_symbol(self, symbol: str, price: Decimal) -> None:
        """
        Quick non-locking scan to find candidate positions.
        Each candidate is then re-verified under a lock before executing.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Position.id, Position.user_id).where(
                    Position.symbol == symbol,
                    Position.quantity > 0,
                    or_(
                        and_(Position.stop_loss.isnot(None), Position.stop_loss >= price),
                        and_(Position.target_price.isnot(None), Position.target_price <= price),
                    ),
                )
            )
            candidates = result.all()

        for row in candidates:
            await self._try_execute(row.id, row.user_id, symbol, price)

    async def _try_execute(
        self,
        position_id: uuid.UUID,
        user_id: uuid.UUID,
        symbol: str,
        price: Decimal,
    ) -> None:
        """
        Atomically verifies, clears, and executes the triggered SL/Target.
        Each candidate gets its own transaction so a failure on one position
        doesn't roll back others.
        """
        async with AsyncSessionLocal() as session:
            try:
                # ── 1. Lock wallet (always first — matches OrderService ordering) ──
                wallet_res = await session.execute(
                    select(Wallet)
                    .where(Wallet.user_id == user_id)
                    .with_for_update()
                    .limit(1)
                )
                wallet = wallet_res.scalar_one_or_none()
                if not wallet:
                    return

                # ── 2. Lock position ──────────────────────────────────────────────
                pos_res = await session.execute(
                    select(Position)
                    .where(Position.id == position_id)
                    .with_for_update()
                    .limit(1)
                )
                pos = pos_res.scalar_one_or_none()
                if not pos or pos.quantity == 0:
                    return

                # ── 3. Re-verify under lock (another concurrent execution may have
                #       already cleared these fields and committed) ──────────────────
                sl_hit = pos.stop_loss is not None and price <= pos.stop_loss
                target_hit = pos.target_price is not None and price >= pos.target_price
                if not sl_hit and not target_hit:
                    return

                reason = "stop_loss" if sl_hit else "target"
                quantity = pos.quantity
                order_value = (price * quantity).quantize(_SCALE)

                # ── 4. Clear triggers FIRST — prevents any duplicate execution ─────
                pos.stop_loss = None
                pos.target_price = None
                pos.quantity = 0
                await session.flush()  # write to DB within this txn; not yet committed

                # ── 5. Credit wallet ──────────────────────────────────────────────
                wallet.balance = (wallet.balance + order_value).quantize(_SCALE)

                # ── 6. Record order + wallet transaction ──────────────────────────
                order_id = uuid.uuid4()
                session.add(
                    WalletTransaction(
                        user_id=user_id,
                        wallet_id=wallet.id,
                        type=TransactionType.CREDIT,
                        amount=order_value,
                        balance_after=wallet.balance,
                        reference_id=str(order_id),
                    )
                )
                session.add(
                    Order(
                        id=order_id,
                        user_id=user_id,
                        symbol=symbol,
                        side=OrderSide.SELL,
                        quantity=quantity,
                        price=price,
                        order_value=order_value,
                        status=OrderStatus.EXECUTED,
                    )
                )

                await session.flush()
                await session.commit()
                log.info(
                    "[%s] %s triggered for user=%s  %s × %s @ ₹%s  "
                    "→ credited ₹%s  new_balance=₹%s",
                    reason,
                    symbol,
                    user_id,
                    quantity,
                    symbol,
                    price,
                    order_value,
                    wallet.balance,
                )

            except Exception as exc:
                await session.rollback()
                log.exception(
                    "Failed SL/Target execution for position=%s: %s", position_id, exc
                )


# module-level singleton — imported by main.py lifespan
stoploss_engine = StopLossService()
