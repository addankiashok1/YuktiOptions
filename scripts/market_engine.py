"""
Market data simulation engine.

Publishes realistic price ticks for NIFTY / BANKNIFTY / FINNIFTY
to Redis channel "market_data" every second.

Usage:
    python scripts/market_engine.py
    python scripts/market_engine.py --interval 0.5
    python scripts/market_engine.py --redis redis://localhost:6379 --channel market_data
"""

import argparse
import asyncio
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import redis.asyncio as aioredis

_DEFAULT_REDIS = "redis://localhost:6379"
_DEFAULT_CHANNEL = "market_data"
_DEFAULT_INTERVAL = 1.0


# ---------------------------------------------------------------------------
# Per-symbol price engine
# ---------------------------------------------------------------------------


@dataclass
class SymbolEngine:
    """
    Maintains realistic price state for a single symbol.

    Price model:
        delta = gaussian_noise + trend + mean_reversion
        price += delta

    - gaussian_noise  → `volatility` std-dev; Gaussian is more realistic than
                         uniform (produces occasional larger swings naturally)
    - trend           → slow directional drift that reverses every 8-30 ticks,
                         capped at 25% of volatility to avoid runaway moves
    - mean_reversion  → 0.2% pull per tick toward base_price; keeps the
                         simulation anchored long-term
    """

    symbol: str
    base_price: float
    volatility: float  # points std-dev per tick

    price: float = field(init=False)
    open_price: float = field(init=False)
    _trend: float = field(default=0.0, init=False, repr=False)
    _trend_ticks: int = field(default=0, init=False, repr=False)
    _trend_life: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.price = self.base_price
        self.open_price = self.base_price
        self._rotate_trend()

    def _rotate_trend(self) -> None:
        max_drift = self.volatility * 0.25
        self._trend = random.uniform(-max_drift, max_drift)
        self._trend_life = random.randint(8, 30)
        self._trend_ticks = 0

    def tick(self) -> dict:
        self._trend_ticks += 1
        if self._trend_ticks >= self._trend_life:
            self._rotate_trend()

        noise = random.gauss(0, self.volatility)
        mean_reversion = (self.base_price - self.price) * 0.002

        self.price = round(max(self.price + noise + self._trend + mean_reversion, 1.0), 2)

        change = round(self.price - self.open_price, 2)
        change_pct = round((change / self.open_price) * 100, 2)

        return {
            "symbol": self.symbol,
            "price": self.price,
            "change": change,
            "change_pct": change_pct,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Symbols  (symbol, base_price, volatility_pts_per_tick)
# ---------------------------------------------------------------------------

_SYMBOLS: list[tuple[str, float, float]] = [
    ("NIFTY",     22450.0,  5.0),
    ("BANKNIFTY", 48320.0, 12.0),
    ("FINNIFTY",  21180.0,  8.0),
]


# ---------------------------------------------------------------------------
# Market engine — orchestrates all symbols and publishes to Redis
# ---------------------------------------------------------------------------


class MarketEngine:
    def __init__(self, redis_url: str, channel: str, interval: float) -> None:
        self._engines = [SymbolEngine(sym, base, vol) for sym, base, vol in _SYMBOLS]
        self._redis_url = redis_url
        self._channel = channel
        self._interval = interval

    async def run(self) -> None:
        client = aioredis.from_url(
            self._redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        print(
            f"Market engine started  channel='{self._channel}'  "
            f"interval={self._interval}s   (Ctrl+C to stop)\n"
        )
        try:
            while True:
                for engine in self._engines:
                    tick = engine.tick()
                    payload = json.dumps(tick)
                    # SET latest price so order service can read on demand
                    await client.set(f"price:{tick['symbol']}", payload)
                    await client.publish(self._channel, payload)
                    sign = "+" if tick["change"] >= 0 else ""
                    print(
                        f"  {tick['symbol']:<10}  "
                        f"₹{tick['price']:>10.2f}  "
                        f"{sign}{tick['change']:>8.2f}  "
                        f"({sign}{tick['change_pct']}%)"
                    )
                print()
                await asyncio.sleep(self._interval)

        except (asyncio.CancelledError, KeyboardInterrupt):
            print("\nMarket engine stopped.")
        finally:
            await client.aclose()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="YuktiOptions market data simulator")
    p.add_argument("--redis", default=_DEFAULT_REDIS, metavar="URL", help="Redis URL")
    p.add_argument("--channel", default=_DEFAULT_CHANNEL, help="Pub/Sub channel name")
    p.add_argument("--interval", type=float, default=_DEFAULT_INTERVAL, metavar="SEC", help="Tick interval in seconds")
    return p.parse_args()


if __name__ == "__main__":
    a = _args()
    asyncio.run(MarketEngine(redis_url=a.redis, channel=a.channel, interval=a.interval).run())
