"""
Standalone price publisher — runs outside FastAPI.
Publishes a NIFTY price tick every second to the Redis "market_data" channel.

Usage:
    python scripts/price_publisher.py
"""

import asyncio
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from the project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import redis.asyncio as aioredis

REDIS_URL = "redis://localhost:6379"
CHANNEL = "market_data"
INTERVAL = 1.0  # seconds

_BASE: dict[str, float] = {
    "NIFTY": 22450.25,
    "BANKNIFTY": 48320.50,
    "SENSEX": 73980.15,
}


async def publish() -> None:
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    print(f"Connected to Redis. Publishing to '{CHANNEL}' every {INTERVAL}s  (Ctrl+C to stop)")
    try:
        while True:
            for symbol, base in _BASE.items():
                payload = json.dumps(
                    {
                        "symbol": symbol,
                        "price": round(base + random.uniform(-100, 100), 2),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                await client.publish(CHANNEL, payload)
                print(payload)
            await asyncio.sleep(INTERVAL)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\nShutting down publisher.")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(publish())
