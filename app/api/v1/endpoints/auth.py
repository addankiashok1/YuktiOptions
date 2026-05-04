from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, DuplicateEmailError, DuplicateMobileError
from app.models.user import User
from app.schemas.user import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    RefreshResponse,
    UserCreate,
    UserResponse,
)
from app.services.user_service import UserService
from app.utils.security import create_access_token, create_refresh_token, decode_refresh_token

router = APIRouter()

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token.",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    try:
        user = await UserService(db).create_user(payload)
    except DuplicateEmailError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except DuplicateMobileError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return UserResponse.model_validate(user)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)

    try:
        user = await svc.authenticate_user(payload.email, payload.password)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    token_data = {"sub": str(user.id)}
    refresh_token = create_refresh_token(token_data)

    await svc.save_refresh_token(user.id, refresh_token)

    return LoginResponse(
        access_token=create_access_token(token_data),
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_payload = decode_refresh_token(payload.refresh_token)

    svc = UserService(db)
    stored = await svc.get_refresh_token(payload.refresh_token)
    if not stored:
        raise _UNAUTHORIZED

    user_id = token_payload["sub"]
    new_refresh = await svc.rotate_refresh_token(payload.refresh_token, stored.user_id)

    return RefreshResponse(
        access_token=create_access_token({"sub": user_id}),
        refresh_token=new_refresh,
    )


@router.post("/logout")
async def logout(payload: LogoutRequest, db: AsyncSession = Depends(get_db)):
    decode_refresh_token(payload.refresh_token)  # raises 401 if invalid/wrong type
    await UserService(db).revoke_refresh_token(payload.refresh_token)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)
