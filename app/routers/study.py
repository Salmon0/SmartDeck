from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_card_or_404, get_current_user, get_deck_or_404, get_session_or_404
from app.models import StudyResult, StudySession, User
from app.schemas import AnswerIn, AnswerOut, NextCardOut, SessionOut
from app.services import scheduler
from app.timeutil import utcnow

router = APIRouter(tags=["study"])


@router.post("/decks/{deck_id}/sessions", response_model=SessionOut,
             status_code=status.HTTP_201_CREATED, summary="Начать учебную сессию по колоде")
def start_session(deck_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    deck = get_deck_or_404(db, deck_id, user)
    session = StudySession(user_id=user.id, deck_id=deck.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[SessionOut], summary="История сессий")
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(StudySession).where(StudySession.user_id == user.id)
                      .order_by(StudySession.id.desc()).limit(100)).all()


@router.get("/sessions/{session_id}/next", response_model=NextCardOut,
            summary="Следующая карточка (card = null, если повторять нечего)")
def next_card(session_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    session = get_session_or_404(db, session_id, user)
    if session.finished_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Сессия уже завершена")
    last_card_id = db.scalar(select(StudyResult.card_id)
                             .where(StudyResult.session_id == session.id)
                             .order_by(StudyResult.id.desc()).limit(1))
    card, remaining = scheduler.get_next_card(db, session.deck_id, exclude_card_id=last_card_id)
    return NextCardOut(card=card, remaining_due=remaining)


@router.post("/sessions/{session_id}/answers", response_model=AnswerOut,
             status_code=status.HTTP_201_CREATED, summary="Отправить результат ответа на карточку")
def submit_answer(session_id: int, data: AnswerIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    session = get_session_or_404(db, session_id, user)
    if session.finished_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Сессия уже завершена")
    card = get_card_or_404(db, data.card_id, user)
    if card.deck_id != session.deck_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Карточка не из колоды этой сессии")

    now = utcnow()
    quality = scheduler.apply_review(card, data.is_correct, data.quality, now)
    db.add(StudyResult(session_id=session.id, card_id=card.id, is_correct=data.is_correct,
                       quality=quality, response_time_ms=data.response_time_ms, answered_at=now))
    session.total_answers += 1
    session.correct_answers += int(data.is_correct)
    db.commit()
    db.refresh(card)
    db.refresh(session)
    return AnswerOut(is_correct=data.is_correct, interval_days=card.interval_days,
                     next_review=card.next_review, session_total=session.total_answers,
                     session_correct=session.correct_answers)


@router.post("/sessions/{session_id}/finish", response_model=SessionOut,
             summary="Завершить сессию (повторный вызов безопасен)")
def finish_session(session_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    session = get_session_or_404(db, session_id, user)
    if session.finished_at is None:
        session.finished_at = utcnow()
        db.commit()
        db.refresh(session)
    return session
