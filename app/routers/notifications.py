from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import NotificationSettings, User
from app.schemas import NotificationIn, NotificationOut, ReminderOut
from app.services import statistics
from app.timeutil import utcnow

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _settings(db: Session, user: User) -> NotificationSettings:
    if user.notification_settings is None:
        user.notification_settings = NotificationSettings()
        db.commit()
        db.refresh(user)
    return user.notification_settings


def _out(s: NotificationSettings) -> NotificationOut:
    days = [int(d) for d in s.days.split(",") if d != ""]
    return NotificationOut(enabled=s.enabled, notify_time=s.notify_time, days=days)


@router.get("", response_model=NotificationOut)
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(_settings(db, user))


@router.put("", response_model=NotificationOut)
def update_settings(data: NotificationIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    s = _settings(db, user)
    s.enabled, s.notify_time = data.enabled, data.notify_time
    s.days = ",".join(str(d) for d in data.days)
    db.commit()
    db.refresh(s)
    return _out(s)


@router.get("/reminder", response_model=ReminderOut,
            summary="Нужно ли напомнить пользователю об уроке сегодня (для WorkManager)")
def reminder(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _settings(db, user)
    due = statistics.overview(db, user.id)["due_cards"]
    today_allowed = utcnow().weekday() in {int(d) for d in s.days.split(",") if d != ""}
    return ReminderOut(should_remind=s.enabled and today_allowed and due > 0, due_cards=due)
