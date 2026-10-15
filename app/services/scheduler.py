"""StudyScheduler из UML: интервальное повторение по алгоритму SM-2.

- верный ответ (оценка >= 3): интервал растёт 1 → 6 → interval * ease дней;
- неверный ответ: карточка сразу снова становится «к повторению» и в сессии
  показывается раньше остальных (после одной другой карточки).
"""
from datetime import datetime, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models import Flashcard
from app.timeutil import utcnow

MIN_EASE = 1.3


def default_quality(is_correct: bool) -> int:
    return 4 if is_correct else 1


def apply_review(card: Flashcard, is_correct: bool, quality: int | None = None,
                 now: datetime | None = None) -> int:
    """Обновляет состояние карточки. Возвращает итоговую оценку 0..5."""
    now = now or utcnow()
    q = default_quality(is_correct) if quality is None else quality
    # is_correct главнее: оценка не должна ему противоречить.
    q = max(q, 3) if is_correct else min(q, 2)

    card.ease = max(MIN_EASE, card.ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    if q < 3:
        card.repetitions = 0
        card.interval_days = 0
        card.next_review = now
        card.wrong_count += 1
    else:
        card.repetitions += 1
        if card.repetitions == 1:
            card.interval_days = 1
        elif card.repetitions == 2:
            card.interval_days = 6
        else:
            card.interval_days = max(1, round(card.interval_days * card.ease))
        card.next_review = now + timedelta(days=card.interval_days)
        card.correct_count += 1
    return q


def _due_filter(deck_id: int, now: datetime):
    return and_(Flashcard.deck_id == deck_id, Flashcard.next_review <= now)


def count_due(db: Session, deck_id: int, now: datetime | None = None) -> int:
    now = now or utcnow()
    return db.scalar(select(func.count(Flashcard.id)).where(_due_filter(deck_id, now))) or 0


def get_next_card(db: Session, deck_id: int, exclude_card_id: int | None = None,
                  now: datetime | None = None) -> tuple[Flashcard | None, int]:
    """Следующая карточка к показу и число оставшихся к повторению в колоде."""
    now = now or utcnow()
    remaining = count_due(db, deck_id, now)
    learning_first = case(
        (and_(Flashcard.repetitions == 0, Flashcard.wrong_count > 0), 0), else_=1)
    candidates = db.scalars(
        select(Flashcard)
        .where(_due_filter(deck_id, now))
        .order_by(learning_first, Flashcard.next_review, Flashcard.id)
        .limit(2)
    ).all()
    for card in candidates:
        if card.id != exclude_card_id:
            return card, remaining
    return (candidates[0] if candidates else None), remaining
