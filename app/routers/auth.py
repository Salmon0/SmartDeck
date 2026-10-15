import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import NotificationSettings, User
from app.schemas import LoginIn, TokenOut, UserCreate, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _authenticate(db: Session, login: str, password: str) -> User:
    key = login.strip().lower()
    user = db.scalar(select(User).where(
        or_(func.lower(User.email) == key, func.lower(User.username) == key)))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    return user


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    email, username = data.email.lower(), data.username.strip()
    taken = db.scalar(select(User).where(
        or_(func.lower(User.email) == email, func.lower(User.username) == username.lower())))
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email или имя пользователя уже заняты")
    user = User(email=email, username=username, password_hash=hash_password(data.password))
    user.notification_settings = NotificationSettings()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = _authenticate(db, data.login, data.password)
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/token", response_model=TokenOut, include_in_schema=True,
             summary="Вход через форму (для кнопки Authorize в Swagger)")
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = _authenticate(db, form.username, form.password)
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_dir = Path(settings.upload_dir) / str(user.id)
    db.delete(user)
    db.commit()
    shutil.rmtree(user_dir, ignore_errors=True)
