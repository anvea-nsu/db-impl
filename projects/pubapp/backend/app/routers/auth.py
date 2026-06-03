import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import AppUser
from app.auth import verify_password, hash_password, create_access_token, get_current_user
from app.schemas import UserRegister, Token, UserOut

log = logging.getLogger("pubapp.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    # Check email uniqueness
    existing = (await db.execute(
        select(AppUser).where(AppUser.email == data.email)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    # Validate password length
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Пароль должен быть не менее 6 символов")

    # First registered user → admin
    count = (await db.execute(select(func.count()).select_from(AppUser))).scalar()
    role = "admin" if count == 0 else "user"

    user = AppUser(
        username=data.username or None,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=role,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except Exception as e:
        await db.rollback()
        log.error(f"Register DB error: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка базы данных: {str(e)}")

    log.info(f"New user registered: {user.email} (role={user.role})")
    return user


@router.post("/token", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    # form_data.username field is used to pass email
    result = await db.execute(select(AppUser).where(AppUser.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт деактивирован")

    token = create_access_token({"sub": user.email})
    return Token(
        access_token=token,
        token_type="bearer",
        role=user.role,
        username=user.username or user.email,
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: AppUser = Depends(get_current_user)):
    return current_user
