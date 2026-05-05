"""
Matching engine — Redis subscriber that drives order_matching_service.

Runs as a persistent background task (started from app lifespan).
Subscribes to "market_data" independently of the WebSocket so orders
execute even when no WebSocket clients are connected.
"""

import asyncio
import json
import logging
from decimal import Decimal

from app.core.redis import get_redis
from app.services.order_matching_service import process_price_update

log = logging.getLogger(__name__)

_CHANNEL = "market_data"


class MatchingEngine:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="matching-engine")
            log.info("Matching engine started.")

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

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
                    price = Decimal(str(tick["price"])).quantize(Decimal("0.01"))
                except Exception:
                    continue

                await process_price_update(symbol, price)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.exception("Matching engine crashed: %s", exc)
        finally:
            await pubsub.unsubscribe(_CHANNEL)
            await pubsub.aclose()
            log.info("Matching engine stopped.")


matching_engine = MatchingEngine()
