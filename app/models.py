"""ORM-модели. Соответствуют классам и таблицам из разделов 3.1–3.2 курсовой.

Сервисные классы (DocumentProcessor, StudyScheduler, Statistics) таблиц не имеют —
они реализованы в app/services. Статус обработки документа хранится в StudyMaterial.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func, select,
)
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.database import Base
from app.timeutil import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    disciplines: Mapped[list["Discipline"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    decks: Mapped[list["Deck"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    materials: Mapped[list["StudyMaterial"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    sessions: Mapped[list["StudySession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    notification_settings: Mapped["NotificationSettings | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)


class Discipline(Base):
    __tablename__ = "disciplines"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="disciplines")


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # При удалении дисциплины колоды не пропадают, а остаются «без дисциплины».
    discipline_id: Mapped[int | None] = mapped_column(
        ForeignKey("disciplines.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="decks")
    # Композиция Deck → Flashcard: карточки удаляются вместе с колодой.
    cards: Mapped[list["Flashcard"]] = relationship(
        back_populates="deck", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Flashcard.id")


class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[int] = mapped_column(primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    # Состояние интервального повторения (алгоритм SM-2).
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    next_review: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    deck: Mapped[Deck] = relationship(back_populates="cards")


Deck.card_count = column_property(
    select(func.count(Flashcard.id))
    .where(Flashcard.deck_id == Deck.id)
    .correlate_except(Flashcard)
    .scalar_subquery()
)


class StudyMaterial(Base):
    __tablename__ = "study_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    deck_id: Mapped[int | None] = mapped_column(ForeignKey("decks.id", ondelete="SET NULL"))
    file_name: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(16))
    stored_path: Mapped[str | None] = mapped_column(String(500))
    # Данные «обработчика документов»: чем обработан и с каким результатом.
    processor_type: Mapped[str | None] = mapped_column(String(32))   # openai | heuristic
    status: Mapped[str] = mapped_column(String(16), default="processing")  # processing | processed | failed
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(back_populates="materials")


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_time: Mapped[str] = mapped_column(String(5), default="19:00")      # HH:MM
    days: Mapped[str] = mapped_column(String(32), default="0,1,2,3,4,5,6")    # 0 = понедельник

    user: Mapped[User] = relationship(back_populates="notification_settings")


class StudySession(Base):
    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    total_answers: Mapped[int] = mapped_column(Integer, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="sessions")
    # Композиция StudySession → StudyResult.
    results: Mapped[list["StudyResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True)


class StudyResult(Base):
    __tablename__ = "study_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("flashcards.id", ondelete="CASCADE"), index=True)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    quality: Mapped[int] = mapped_column(Integer)                 # 0..5, шкала SM-2
    response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    answered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    session: Mapped[StudySession] = relationship(back_populates="results")
