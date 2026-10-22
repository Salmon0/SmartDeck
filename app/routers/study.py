from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_card_or_404, get_current_user, get_deck_or_404, get_session_or_404
from app.models import Flashcard, StudyResult, StudySession, User
from app.schemas import AnswerIn, AnswerOut, NextCardOut, SessionOut, SessionSummaryOut
from app.services import scheduler
from app.timeutil import utcnow

router = APIRouter(tags=["study"])


@router.post("/decks/{deck_id}/sessions", response_model=SessionOut,
             status_code=status.HTTP_201_CREATED, summary="Начать учебную сессию по колоде")
def start_session(deck_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db), mode: str = "auto"):
    deck = get_deck_or_404(db, deck_id, user)
    if mode not in {"auto", "due", "all"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "mode должен быть auto, due или all")
    if mode == "auto":
        mode = "due" if scheduler.count_due(db, deck.id) else "all"
    session = StudySession(user_id=user.id, deck_id=deck.id, mode=mode)
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
    answered_ids = select(StudyResult.card_id).where(StudyResult.session_id == session.id).distinct()
    if session.mode == "all":
        last_attempt = (select(StudyResult.card_id.label("card_id"),
                               func.max(StudyResult.id).label("last_id"))
                        .where(StudyResult.session_id == session.id)
                        .group_by(StudyResult.card_id).subquery())
        missed_ids = (select(StudyResult.card_id)
                      .join(last_attempt, StudyResult.id == last_attempt.c.last_id)
                      .where(StudyResult.is_correct.is_(False)))
        unattempted = db.scalars(select(Flashcard).where(
            Flashcard.deck_id == session.deck_id,
            Flashcard.id.not_in(answered_ids),
        ).order_by(Flashcard.id).limit(2)).all()
        card = next((item for item in unattempted if item.id != last_card_id), None)
        if card is None and unattempted:
            card = unattempted[0]
        if card is None:
            # Repeat missed cards after all new cards have been seen.
            repeat = db.scalars(select(Flashcard).where(
                Flashcard.deck_id == session.deck_id,
                Flashcard.id.in_(missed_ids),
            ).order_by(Flashcard.id).limit(2)).all()
            card = next((item for item in repeat if item.id != last_card_id), None)
            if card is None and repeat:
                card = repeat[0]
        remaining_new = db.scalar(select(func.count(Flashcard.id)).where(
            Flashcard.deck_id == session.deck_id, Flashcard.id.not_in(answered_ids))) or 0
        remaining_repeat = db.scalar(select(func.count()).select_from(missed_ids.subquery())) or 0
        remaining_due = scheduler.count_due(db, session.deck_id)
    else:
        card, remaining_due = scheduler.get_next_card(
            db, session.deck_id, exclude_card_id=last_card_id)
        due_unseen = (select(Flashcard.id).where(
            Flashcard.deck_id == session.deck_id,
            Flashcard.next_review <= utcnow(),
            Flashcard.id.not_in(answered_ids),
        ))
        remaining_new = db.scalar(select(func.count()).select_from(due_unseen.subquery())) or 0
        remaining_repeat = max(0, remaining_due - remaining_new)
    return NextCardOut(card=card, remaining_due=remaining_due,
                       remaining_new=remaining_new, remaining_repeat=remaining_repeat)


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
    if session.mode == "all":
        quality = data.quality if data.quality is not None else (4 if data.is_correct else 1)
    else:
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


@router.post("/sessions/{session_id}/finish", response_model=SessionSummaryOut,
             summary="Завершить сессию (повторный вызов безопасен)")
def finish_session(session_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    session = get_session_or_404(db, session_id, user)
    if session.finished_at is None:
        session.finished_at = utcnow()
        db.commit()
        db.refresh(session)
    active_ms = db.scalar(select(func.coalesce(func.sum(StudyResult.response_time_ms), 0))
                          .where(StudyResult.session_id == session.id)) or 0
    duration = max(0, int((session.finished_at - session.started_at).total_seconds()))
    return SessionSummaryOut(
        total_answers=session.total_answers,
        correct_answers=session.correct_answers,
        wrong_answers=session.total_answers - session.correct_answers,
        active_seconds=int(active_ms / 1000),
        duration_seconds=duration,
    )
