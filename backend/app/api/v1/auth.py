from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_current_user, verify_password
from app.db.models import AuditLog, User
from app.db.session import get_session
from app.schemas.admin import LoginRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


async def _authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = (
        await session.execute(select(User).where(User.email == email.lower().strip()))
    ).scalars().first()
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    session.add(
        AuditLog(
            actor_id=user.id,
            actor_email=user.email,
            action="auth.login",
            target_type="user",
            target_id=str(user.id),
            details={"role": user.role.value},
        )
    )
    await session.commit()
    return user


@router.post("/login", response_model=TokenOut)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenOut:
    user = await _authenticate(session, payload.email, payload.password)
    return TokenOut(
        access_token=create_access_token(user), role=user.role, email=user.email
    )


@router.post("/token", response_model=TokenOut, include_in_schema=False)
async def login_form(
    form: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    """OAuth2 password-flow shape, so Swagger's Authorize button works."""
    user = await _authenticate(session, form.username, form.password)
    return TokenOut(access_token=create_access_token(user), role=user.role, email=user.email)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
