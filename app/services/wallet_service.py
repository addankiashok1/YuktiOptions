import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientBalanceError, WalletNotFoundError
from app.models.wallet import Wallet
from app.models.wallet_transaction import TransactionType, WalletTransaction

_SCALE = Decimal("0.01")


class WalletService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_wallet(self, user_id: uuid.UUID) -> Wallet:
        result = await self.db.execute(
            select(Wallet).where(Wallet.user_id == user_id).limit(1)
        )
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise WalletNotFoundError("Wallet not found.")
        return wallet

    async def get_balance(self, user_id: uuid.UUID) -> Decimal:
        wallet = await self.get_wallet(user_id)
        return wallet.balance

    async def get_transactions(self, user_id: uuid.UUID) -> list[WalletTransaction]:
        # Verify wallet exists before fetching transactions
        await self.get_wallet(user_id)
        result = await self.db.execute(
            select(WalletTransaction)
            .where(WalletTransaction.user_id == user_id)
            .order_by(WalletTransaction.created_at.desc())
        )
        return list(result.scalars().all())

    async def credit(
        self,
        user_id: uuid.UUID,
        amount: Decimal,
        reference_id: str | None = None,
    ) -> WalletTransaction:
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        amount = amount.quantize(_SCALE)

        result = await self.db.execute(
            select(Wallet)
            .where(Wallet.user_id == user_id)
            .with_for_update()
            .limit(1)
        )
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise WalletNotFoundError("Wallet not found.")

        wallet.balance = (wallet.balance + amount).quantize(_SCALE)

        tx = WalletTransaction(
            user_id=user_id,
            wallet_id=wallet.id,
            type=TransactionType.CREDIT,
            amount=amount,
            balance_after=wallet.balance,
            reference_id=reference_id,
        )
        self.db.add(tx)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(tx)
        return tx

    async def debit(
        self,
        user_id: uuid.UUID,
        amount: Decimal,
        reference_id: str | None = None,
    ) -> WalletTransaction:
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        amount = amount.quantize(_SCALE)

        result = await self.db.execute(
            select(Wallet)
            .where(Wallet.user_id == user_id)
            .with_for_update()
            .limit(1)
        )
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise WalletNotFoundError("Wallet not found.")

        if wallet.balance < amount:
            raise InsufficientBalanceError("Insufficient balance.")

        wallet.balance = (wallet.balance - amount).quantize(_SCALE)

        tx = WalletTransaction(
            user_id=user_id,
            wallet_id=wallet.id,
            type=TransactionType.DEBIT,
            amount=amount,
            balance_after=wallet.balance,
            reference_id=reference_id,
        )
        self.db.add(tx)
        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(tx)
        return tx

    async def create_wallet(self, user_id: uuid.UUID) -> Wallet:
        wallet = Wallet(user_id=user_id, balance=Decimal("0"))
        self.db.add(wallet)
        await self.db.commit()
        await self.db.refresh(wallet)
        return wallet
