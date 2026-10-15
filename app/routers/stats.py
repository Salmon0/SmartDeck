from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import OverviewOut, WeeklyReportOut
from app.services import statistics

router = APIRouter(prefix="/stats", tags=["statistics"])


@router.get("/overview", response_model=OverviewOut,
            summary="Общая статистика (has_data = false до первой сессии)")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return statistics.overview(db, user.id)


@router.get("/weekly", response_model=WeeklyReportOut, summary="Недельный отчёт")
def weekly(day: date | None = Query(default=None, description="Любая дата нужной недели; по умолчанию — текущая"),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return statistics.weekly_report(db, user.id, day)
