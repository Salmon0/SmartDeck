import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class UserOut(ORM):
    id: int
    email: str
    username: str
    created_at: datetime


class LoginIn(BaseModel):
    login: str = Field(description="Имя пользователя или email")
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- disciplines ----------
class DisciplineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class DisciplineUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class DisciplineOut(ORM):
    id: int
    name: str
    description: str
    created_at: datetime


# ---------- cards ----------
class CardCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=5000)


class CardUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    answer: str | None = Field(default=None, min_length=1, max_length=5000)


class CardOut(ORM):
    id: int
    deck_id: int
    question: str
    answer: str
    interval_days: int
    ease: float
    repetitions: int
    next_review: datetime
    correct_count: int
    wrong_count: int


# ---------- decks ----------
class DeckCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    discipline_id: int | None = None


class DeckUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    discipline_id: int | None = None  # явный null снимает дисциплину


class DeckOut(ORM):
    id: int
    title: str
    discipline_id: int | None
    created_at: datetime
    card_count: int
    due_count: int = 0


class DeckDetail(DeckOut):
    cards: list[CardOut]


# ---------- materials ----------
class MaterialOut(ORM):
    id: int
    file_name: str
    file_format: str
    status: str
    processor_type: str | None
    error: str | None
    deck_id: int | None
    created_at: datetime


class MaterialUploadOut(BaseModel):
    material: MaterialOut
    deck: DeckOut


# ---------- study ----------
class SessionOut(ORM):
    id: int
    deck_id: int
    started_at: datetime
    finished_at: datetime | None
    total_answers: int
    correct_answers: int


class NextCardOut(BaseModel):
    card: CardOut | None
    remaining_due: int


class AnswerIn(BaseModel):
    card_id: int
    is_correct: bool
    quality: int | None = Field(
        default=None, ge=0, le=5,
        description="Необязательная оценка по шкале SM-2 (0 — забыл, 5 — идеально)")
    response_time_ms: int = Field(default=0, ge=0, le=3_600_000)


class AnswerOut(BaseModel):
    is_correct: bool
    interval_days: int
    next_review: datetime
    session_total: int
    session_correct: int


# ---------- statistics ----------
class OverviewOut(BaseModel):
    has_data: bool
    accuracy_percent: float | None
    total_answers: int
    total_sessions: int
    total_decks: int
    total_cards: int
    due_cards: int


class DailyActivity(BaseModel):
    date: date
    cards_answered: int
    correct_answers: int
    study_seconds: int


class WeeklyReportOut(BaseModel):
    start_date: date
    end_date: date
    has_data: bool
    learned_cards: int
    total_answers: int
    accuracy_percent: float | None
    total_study_seconds: int
    daily_activity: list[DailyActivity]


# ---------- notifications ----------
class NotificationIn(BaseModel):
    enabled: bool
    notify_time: str = Field(default="19:00", description="HH:MM")
    days: list[int] = Field(default_factory=lambda: list(range(7)),
                            description="Дни недели, 0 = понедельник")

    @field_validator("notify_time")
    @classmethod
    def _check_time(cls, v: str) -> str:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("Ожидается формат HH:MM")
        return v

    @field_validator("days")
    @classmethod
    def _check_days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("Дни недели должны быть в диапазоне 0..6")
        return sorted(set(v))


class NotificationOut(BaseModel):
    enabled: bool
    notify_time: str
    days: list[int]


class ReminderOut(BaseModel):
    should_remind: bool
    due_cards: int
