import asyncio
from functools import partial

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateEmailError, DuplicateMobileError
from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
