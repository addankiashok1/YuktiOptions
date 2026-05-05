"""
Order matching service — stateless business logic.

Exposes one public coroutine:

    await process_price_update(symbol, price)

Call it from any code that receives a live price (Redis consumer, WebSocket
listener, etc.). It handles two-phase matching in a single async call:

  Phase 1 — STOP_LIMIT orders whose trigger price has been hit
             → status: PENDING → TRIGGERED
             → if limit condition is also met in the same tick, skip straight to Phase 2

  Phase 2 — LIMIT orders (PENDING) and triggered STOP_LIMIT orders (TRIGGERED)
             whose limit price condition is satisfied
             → status: TRIGGERED/PENDING → EXECUTED

Duplicate-execution safety
--------------------------
Every order mutation (trigger / execute) starts with SELECT … FOR UPDATE on the
order row and re-checks status under that lock.  If two callers race on the same
order, the second will see a terminal status (EXECUTED / FAILED / TRIGGERED) and
return without side effects.

Lock ordering inside _execute_order:  order → wallet → position
  OrderService uses wallet → position (no order lock), so there is no cycle
  between concurrent user-placed market orders and matching-engine executions.
"""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.order import Order, OrderSide, OrderStatus, OrderType
from app.models.position import Position
from app.models.wallet import Wallet
from app.models.wallet_transaction import TransactionType, WalletTransaction

log = logging.getLogger(__name__)

_SCALE = Decimal("0.01")


# ── condition predicates (pure, no I/O) ───────────────────────────────────────

def _triggers(side: OrderSide, trigger_price: Decimal, market_price: Decimal) -> bool:
    """True when a STOP_LIMIT order's trigger condition is met."""
    return market_price >= trigger_price if side == OrderSide.BUY else market_price <= trigger_price


def _executable(side: OrderSide, limit_price: Decimal, market_price: Decimal) -> bool:
    """True when a LIMIT / triggered STOP_LIMIT order should execute."""
    return market_price <= limit_price if side == OrderSide.BUY else market_price >= limit_price


# ── public entry point ────────────────────────────────────────────────────────

async def process_price_update(symbol: str, price: Decimal) -> None:
    """
    Check and execute all pending orders for *symbol* at *price*.
    Safe to call concurrently from multiple subscribers — locks prevent double execution.
    """
    try:
        candidates = await _scan(symbol)
        if not candidates:
            return

        # ── Phase 1: trigger STOP_LIMIT orders ───────────────────────────────
        for order in candidates:
            if order.order_type != OrderType.STOP_LIMIT:
                continue
            if order.status != OrderStatus.PENDING:
                continue
            if not _triggers(order.side, order.trigger_price, price):
                continue

            # Already satisfies the limit condition too → execute directly
            if _executable(order.side, order.limit_price, price):
                await _execute_order(order, price)
            else:
                await _trigger_order(order.id)

        # ── Phase 2: execute LIMIT (pending) + STOP_LIMIT (triggered) ────────
        # Re-scan so orders just triggered in Phase 1 are visible.
        candidates = await _scan(symbol)
        for order in candidates:
            is_limit_pending = (
                order.order_type == OrderType.LIMIT
                and order.status == OrderStatus.PENDING
            )
            is_stop_triggered = (
                order.order_type == OrderType.STOP_LIMIT
                and order.status == OrderStatus.TRIGGERED
            )
            if not (is_limit_pending or is_stop_triggered):
                continue
            if not _executable(order.side, order.limit_price, price):
                continue

            await _execute_order(order, price)

    except Exception as exc:
        log.exception("process_price_update error  symbol=%s price=%s  %s", symbol, price, exc)


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _scan(symbol: str) -> list[Order]:
    """Non-locking scan — returns ORM objects for rich enum/type mapping."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order).where(
                Order.symbol == symbol,
                Order.status.in_([OrderStatus.PENDING, OrderStatus.TRIGGERED]),
            )
        )
        return list(result.scalars().all())


async def _trigger_order(order_id: uuid.UUID) -> None:
    """PENDING → TRIGGERED (no wallet / position changes)."""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(Order).where(Order.id == order_id).with_for_update().limit(1)
            )
            order = result.scalar_one_or_none()
            if not order or order.status != OrderStatus.PENDING:
                return  # Already mutated by a concurrent call
            order.status = OrderStatus.TRIGGERED
            await session.flush()
            await session.commit()
            log.info("[TRIGGERED]  order=%s  %s %s", order_id, order.symbol, order.side.value)
        except Exception as exc:
            await session.rollback()
            log.exception("[TRIGGER ERROR]  order=%s  %s", order_id, exc)


async def _execute_order(order_snapshot: Order, price: Decimal) -> None:
    """
    Execute a limit/stop_limit order atomically.
    Re-acquires SELECT FOR UPDATE to prevent double execution.
    """
    order_id = order_snapshot.id
    user_id = order_snapshot.user_id
    symbol = order_snapshot.symbol
    side = order_snapshot.side
    quantity = order_snapshot.quantity

    async with AsyncSessionLocal() as session:
        try:
            # ── 1. Lock order — re-verify status under lock ───────────────────
            order_res = await session.execute(
                select(Order).where(Order.id == order_id).with_for_update().limit(1)
            )
            order = order_res.scalar_one_or_none()
            if not order or order.status not in (OrderStatus.PENDING, OrderStatus.TRIGGERED):
                return  # Another execution path already claimed this order

            order_value = (price * Decimal(quantity)).quantize(_SCALE)

            # ── 2. Lock wallet ────────────────────────────────────────────────
            wallet_res = await session.execute(
                select(Wallet).where(Wallet.user_id == user_id).with_for_update().limit(1)
            )
            wallet = wallet_res.scalar_one_or_none()
            if not wallet:
                order.status = OrderStatus.FAILED
                await session.flush()
                await session.commit()
                return

            # ── 3. BUY path ───────────────────────────────────────────────────
            if side == OrderSide.BUY:
                if wallet.balance < order_value:
                    order.status = OrderStatus.FAILED
                    await session.flush()
                    await session.commit()
                    log.warning(
                        "[FAILED] order=%s  insufficient balance  need=₹%s  have=₹%s",
                        order_id, order_value, wallet.balance,
                    )
                    return

                pos_res = await session.execute(
                    select(Position)
                    .where(Position.user_id == user_id, Position.symbol == symbol)
                    .with_for_update()
                    .limit(1)
                )
                position = pos_res.scalar_one_or_none()
                if position is None:
                    position = Position(
                        user_id=user_id, symbol=symbol,
                        quantity=0, avg_price=Decimal("0"),
                    )
                    session.add(position)
                    await session.flush()  # get PK assigned

                wallet.balance = (wallet.balance - order_value).quantize(_SCALE)
                new_qty = position.quantity + quantity
                position.avg_price = (
                    (position.avg_price * position.quantity + price * quantity) / new_qty
                ).quantize(_SCALE)
                position.quantity = new_qty
                tx_type = TransactionType.DEBIT

            # ── 4. SELL path ──────────────────────────────────────────────────
            else:
                pos_res = await session.execute(
                    select(Position)
                    .where(Position.user_id == user_id, Position.symbol == symbol)
                    .with_for_update()
                    .limit(1)
                )
                position = pos_res.scalar_one_or_none()
                held = position.quantity if position else 0
                if held < quantity:
                    order.status = OrderStatus.FAILED
                    await session.flush()
                    await session.commit()
                    log.warning(
                        "[FAILED] order=%s  insufficient position  held=%d  need=%d",
                        order_id, held, quantity,
                    )
                    return

                position.quantity -= quantity
                wallet.balance = (wallet.balance + order_value).quantize(_SCALE)
                tx_type = TransactionType.CREDIT

            # ── 5. Record wallet transaction ──────────────────────────────────
            session.add(
                WalletTransaction(
                    user_id=user_id,
                    wallet_id=wallet.id,
                    type=tx_type,
                    amount=order_value,
                    balance_after=wallet.balance,
                    reference_id=str(order_id),
                )
            )

            # ── 6. Stamp execution on the order ───────────────────────────────
            order.price = price
            order.order_value = order_value
            order.status = OrderStatus.EXECUTED

            await session.flush()
            await session.commit()
            log.info(
                "[EXECUTED]  order=%s  %s %s × %s @ ₹%s  value=₹%s  wallet=₹%s",
                order_id, side.value, quantity, symbol, price, order_value, wallet.balance,
            )

        except Exception as exc:
            await session.rollback()
            log.exception("[EXECUTE ERROR]  order=%s  %s", order_id, exc)
