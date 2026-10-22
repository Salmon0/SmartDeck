from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Deck, Discipline, Flashcard, StudySession, User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user_id = decode_access_token(token)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Недействительный токен",
            headers={"WWW-Authenticate": "Bearer"})
    return user


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} не найден(а)")


def get_discipline_or_404(db: Session, discipline_id: int, user: User) -> Discipline:
    obj = db.get(Discipline, discipline_id)
    if obj is None or obj.user_id != user.id:
        raise _not_found("Дисциплина")
    return obj


def get_deck_or_404(db: Session, deck_id: int, user: User) -> Deck:
    obj = db.get(Deck, deck_id)
    if obj is None or obj.user_id != user.id:
        raise _not_found("Колода")
    return obj


def get_card_or_404(db: Session, card_id: int, user: User) -> Flashcard:
    obj = db.get(Flashcard, card_id)
    if obj is None or obj.deck.user_id != user.id:
        raise _not_found("Карточка")
    return obj


def get_session_or_404(db: Session, session_id: int, user: User) -> StudySession:
    obj = db.get(StudySession, session_id)
    if obj is None or obj.user_id != user.id:
        raise _not_found("Сессия")
    return obj
