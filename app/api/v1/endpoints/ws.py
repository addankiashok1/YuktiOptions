import asyncio
import json
import time
import uuid
from decimal import Decimal

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis import get_redis
from app.models.position import Position
from app.services.order_matching_service import process_price_update
from app.utils.security import decode_token

router = APIRouter()

_CHANNEL = "market_data"
_SCALE = Decimal("0.01")
_POSITION_REFRESH_SECS = 30  # re-query DB this often to pick up new orders


# ── market broadcast (unauthenticated, all clients) ───────────────────────────


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: list[WebSocket] = []
        self._task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.append(websocket)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._redis_listener())

    def disconnect(self, websocket: WebSocket) -> None:
        try:
            self._clients.remove(websocket)
        except ValueError:
            pass
        if not self._clients and self._task and not self._task.done():
            self._task.cancel()

    async def _broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def _redis_listener(self) -> None:
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                await self._broadcast(data)
                # Drive order matching on every live price tick
                try:
                    symbol = data["symbol"]
                    price = Decimal(str(data["price"])).quantize(Decimal("0.01"))
                    await process_price_update(symbol, price)
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            await pubsub.unsubscribe(_CHANNEL)
            await pubsub.aclose()


manager = ConnectionManager()


@router.websocket("/market")
async def market_ws(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)


# ── portfolio stream (authenticated, per-user) ────────────────────────────────


async def _load_positions(user_id: uuid.UUID) -> list[dict]:
    """Short-lived DB session — returns plain dicts so the session can close."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Position)
            .where(Position.user_id == user_id, Position.quantity > 0)
        )
        return [
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "avg_price": p.avg_price,  # Decimal from Numeric column
            }
            for p in result.scalars().all()
        ]


def _calc_portfolio(
    positions: list[dict],
    prices: dict[str, Decimal],
) -> dict:
    enriched = []
    total_invested = Decimal("0")
    total_value = Decimal("0")

    for pos in positions:
        avg = pos["avg_price"]
        qty = pos["quantity"]
        current = prices.get(pos["symbol"], avg)  # fallback: no P&L shown if price missing

        invested = (avg * qty).quantize(_SCALE)
        current_value = (current * qty).quantize(_SCALE)
        pnl = (current_value - invested).quantize(_SCALE)
        pnl_pct = (pnl / invested * 100).quantize(_SCALE) if invested else Decimal("0")

        total_invested += invested
        total_value += current_value

        enriched.append(
            {
                "symbol": pos["symbol"],
                "quantity": qty,
                "avg_price": str(avg),
                "current_price": str(current),
                "pnl": str(pnl),
                "pnl_pct": str(pnl_pct),
            }
        )

    total_pnl = (total_value - total_invested).quantize(_SCALE)
    total_pnl_pct = (
        (total_pnl / total_invested * 100).quantize(_SCALE)
        if total_invested
        else Decimal("0")
    )

    return {
        "positions": enriched,
        "total_invested": str(total_invested),
        "portfolio_value": str(total_value),
        "total_pnl": str(total_pnl),
        "total_pnl_pct": str(total_pnl_pct),
    }


@router.websocket("/portfolio")
async def portfolio_ws(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
) -> None:
    # Validate token before accepting — client receives 403 on failure
    try:
        payload = decode_token(token)
        user_id = uuid.UUID(payload["sub"])
    except Exception:
        await websocket.close(code=1008)  # 1008 = Policy Violation
        return

    await websocket.accept()

    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(_CHANNEL)

    # Local caches — all P&L maths happen in memory, no DB per tick
    prices: dict[str, Decimal] = {}
    positions: list[dict] = await _load_positions(user_id)
    last_refresh = time.monotonic()

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                tick = json.loads(message["data"])
                prices[tick["symbol"]] = Decimal(str(tick["price"])).quantize(_SCALE)
            except Exception:
                continue

            # Refresh positions from DB every 30 s to capture new orders
            now = time.monotonic()
            if now - last_refresh >= _POSITION_REFRESH_SECS:
                positions = await _load_positions(user_id)
                last_refresh = now

            portfolio = _calc_portfolio(positions, prices)

            try:
                await websocket.send_json({"type": "portfolio", "data": portfolio})
            except Exception:
                break  # client gone — exit cleanly

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(_CHANNEL)
        await pubsub.aclose()
