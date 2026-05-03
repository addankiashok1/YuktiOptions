from fastapi import APIRouter

from app.api.v1.endpoints import auth, market, orders, wallet, positions, emotion

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(market.router, prefix="/market", tags=["market"])
router.include_router(orders.router, prefix="/orders", tags=["orders"])
router.include_router(wallet.router, prefix="/wallet", tags=["wallet"])
router.include_router(positions.router, prefix="/positions", tags=["positions"])
router.include_router(emotion.router, prefix="/emotion", tags=["emotion"])
