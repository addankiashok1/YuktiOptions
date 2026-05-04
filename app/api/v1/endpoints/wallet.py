from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import WalletNotFoundError
from app.models.user import User
from app.schemas.wallet import TransactionListResponse, TransactionResponse, WalletResponse
from app.services.wallet_service import WalletService

router = APIRouter()


@router.get("", response_model=WalletResponse)
async def get_wallet(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        wallet = await WalletService(db).get_wallet(current_user.id)
    except WalletNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found.")
    return WalletResponse.model_validate(wallet)


@router.get("/transactions", response_model=TransactionListResponse)
async def get_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        transactions = await WalletService(db).get_transactions(current_user.id)
    except WalletNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found.")
    return TransactionListResponse(
        transactions=[TransactionResponse.model_validate(t) for t in transactions],
        total=len(transactions),
    )
