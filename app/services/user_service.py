import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from functools import partial

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, DuplicateEmailError, DuplicateMobileError
from app.core.security import hash_password, verify_password
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import UserCreate
from app.utils.security import create_access_token, create_refresh_token

from app.models.wallet import Wallet
from decimal import Decimal

_REFRESH_EXPIRE_DAYS = 7


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── registration ──────────────────────────────────────────────────────────

    async def create_user(self, payload: UserCreate) -> User:
        await self._assert_email_unique(payload.email.lower())

        if payload.mobile:
            await self._assert_mobile_unique(payload.mobile)

        hashed = await asyncio.get_event_loop().run_in_executor(
            None, partial(hash_password, payload.password)
        )

        user = User(
            email=payload.email.lower(),
            mobile=payload.mobile,
            password_hash=hashed,
        )
        self.db.add(user)

        await self.db.flush()

        wallet = Wallet(
            user_id=user.id,
            balance=Decimal("500000.00")  # 5 lakh
        )

        self.db.add(wallet)
        await self.db.commit()

        try:
            await self.db.commit()
        except IntegrityError as e:
            await self.db.rollback()
            msg = str(e.orig)
            if "email" in msg:
                raise DuplicateEmailError("Email is already registered.")
            if "mobile" in msg:
                raise DuplicateMobileError("Mobile is already registered.")
            raise

        await self.db.refresh(user)
        return user

    # ── authentication ────────────────────────────────────────────────────────

    async def authenticate_user(self, email: str, password: str) -> User:
        result = await self.db.execute(
            select(User).where(User.email == email.lower()).limit(1)
        )
        user = result.scalar_one_or_none()

        _invalid = AuthenticationError("Invalid email or password.")

        if not user:
            raise _invalid

        ok = await asyncio.get_event_loop().run_in_executor(
            None, partial(verify_password, password, user.password_hash)
        )
        if not ok:
            raise _invalid

        return user

    # ── refresh token management ──────────────────────────────────────────────

    async def save_refresh_token(self, user_id: uuid.UUID, token: str) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=_REFRESH_EXPIRE_DAYS)
        self.db.add(RefreshToken(user_id=user_id, token=token, expires_at=expires_at))
        await self.db.commit()

    async def rotate_refresh_token(self, old_token: str, user_id: uuid.UUID) -> str:
        """Delete old token, issue and persist a new one."""
        await self.db.execute(
            delete(RefreshToken).where(RefreshToken.token == old_token)
        )
        new_token = create_refresh_token({"sub": str(user_id)})
        expires_at = datetime.now(timezone.utc) + timedelta(days=_REFRESH_EXPIRE_DAYS)
        self.db.add(RefreshToken(user_id=user_id, token=new_token, expires_at=expires_at))
        await self.db.commit()
        return new_token

    async def revoke_refresh_token(self, token: str) -> None:
        await self.db.execute(
            delete(RefreshToken).where(RefreshToken.token == token)
        )
        await self.db.commit()

    async def get_refresh_token(self, token: str) -> RefreshToken | None:
        result = await self.db.execute(
            select(RefreshToken).where(RefreshToken.token == token).limit(1)
        )
        return result.scalar_one_or_none()

    # ── private helpers ───────────────────────────────────────────────────────

    async def _assert_email_unique(self, email: str) -> None:
        result = await self.db.execute(
            select(User.id).where(User.email == email).limit(1)
        )
        if result.scalar_one_or_none():
            raise DuplicateEmailError(f"Email '{email}' is already registered.")

    async def _assert_mobile_unique(self, mobile: str) -> None:
        result = await self.db.execute(
            select(User.id).where(User.mobile == mobile).limit(1)
        )
        if result.scalar_one_or_none():
            raise DuplicateMobileError(f"Mobile '{mobile}' is already registered.")
