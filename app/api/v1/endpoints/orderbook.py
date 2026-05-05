from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.orderbook import OrderBookResponse
from app.schemas.order import _ALLOWED_SYMBOLS
from app.services.orderbook_service import OrderBookService

router = APIRouter()

_SYMBOL_QUERY = Query(..., description=f"One of: {sorted(_ALLOWED_SYMBOLS)}")


@router.get("", response_model=OrderBookResponse)
async def get_order_book(
    symbol: str = _SYMBOL_QUERY,
    db: AsyncSession = Depends(get_db),
):
    return await OrderBookService(db).get_order_book(symbol.upper())
