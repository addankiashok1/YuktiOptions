from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.position import Position
from app.models.user import User
from app.schemas.position import PositionListResponse, PositionResponse

router = APIRouter()


@router.get("", response_model=PositionListResponse)
async def list_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Position)
        .where(Position.user_id == current_user.id, Position.quantity > 0)
        .order_by(Position.symbol)
    )
    positions = result.scalars().all()
    return PositionListResponse(
        positions=[PositionResponse.model_validate(p) for p in positions]
    )
