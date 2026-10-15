"""Statistics из UML: точность, число выученных карточек, время, недельный отчёт."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from app.models import Deck, Flashcard, StudyResult, StudySession
from app.timeutil import utcnow


def _percent(correct: int, total: int) -> float | None:
    return round(100 * correct / total, 1) if total else None


def overview(db: Session, user_id: int) -> dict:
    total, correct = db.execute(
        select(func.count(StudyResult.id),
               func.coalesce(func.sum(StudyResult.is_correct.cast(Integer)), 0))
        .join(StudySession).where(StudySession.user_id == user_id)
    ).one()
    sessions = db.scalar(select(func.count(StudySession.id)).where(StudySession.user_id == user_id)) or 0
    decks = db.scalar(select(func.count(Deck.id)).where(Deck.user_id == user_id)) or 0
    cards = db.scalar(
        select(func.count(Flashcard.id)).join(Deck).where(Deck.user_id == user_id)) or 0
    due = db.scalar(
        select(func.count(Flashcard.id)).join(Deck)
        .where(Deck.user_id == user_id, Flashcard.next_review <= utcnow())) or 0
    return {
        "has_data": total > 0,  # до первой сессии статистика не показывается
        "accuracy_percent": _percent(int(correct), total),
        "total_answers": total,
        "total_sessions": sessions,
        "total_decks": decks,
        "total_cards": cards,
        "due_cards": due,
    }


def week_start_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def weekly_report(db: Session, user_id: int, any_day: date | None = None) -> dict:
    start = week_start_of(any_day or utcnow().date())
    start_dt = datetime.combine(start, time.min)
    end_dt = start_dt + timedelta(days=7)

    rows = db.execute(
        select(StudyResult.card_id, StudyResult.is_correct,
               StudyResult.response_time_ms, StudyResult.answered_at)
        .join(StudySession)
        .where(StudySession.user_id == user_id,
               StudyResult.answered_at >= start_dt, StudyResult.answered_at < end_dt)
    ).all()

    daily = {start + timedelta(days=i): [0, 0, 0] for i in range(7)}  # ответы, верные, мс
    learned: set[int] = set()
    for card_id, is_correct, ms, answered_at in rows:
        bucket = daily[answered_at.date()]
        bucket[0] += 1
        bucket[2] += ms
        if is_correct:
            bucket[1] += 1
            learned.add(card_id)

    total = sum(b[0] for b in daily.values())
    correct = sum(b[1] for b in daily.values())
    return {
        "start_date": start,
        "end_date": start + timedelta(days=6),
        "has_data": total > 0,
        "learned_cards": len(learned),
        "total_answers": total,
        "accuracy_percent": _percent(correct, total),
        "total_study_seconds": round(sum(b[2] for b in daily.values()) / 1000),
        "daily_activity": [
            {"date": d, "cards_answered": b[0], "correct_answers": b[1],
             "study_seconds": round(b[2] / 1000)}
            for d, b in daily.items()
        ],
    }
