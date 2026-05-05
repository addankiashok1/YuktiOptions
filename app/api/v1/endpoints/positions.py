from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.position import Position
from app.models.user import User
from app.schemas.position import (
    PositionListResponse,
    PositionResponse,
    UpdateSLRequest,
    UpdateSLResponse,
)

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


@router.post("/update-sl", response_model=UpdateSLResponse)
async def update_stop_loss(
    payload: UpdateSLRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Position).where(
            Position.user_id == current_user.id,
            Position.symbol == payload.symbol,
            Position.quantity > 0,
        )
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No open position found for symbol '{payload.symbol}'.",
        )

    position.stop_loss = payload.stop_loss
    position.target_price = payload.target_price
    await db.commit()

    return UpdateSLResponse.model_validate(position)
