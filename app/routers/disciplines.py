from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_discipline_or_404
from app.models import Discipline, User
from app.schemas import DisciplineCreate, DisciplineOut, DisciplineUpdate

router = APIRouter(prefix="/disciplines", tags=["disciplines"])


@router.get("", response_model=list[DisciplineOut])
def list_disciplines(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Discipline).where(Discipline.user_id == user.id).order_by(Discipline.name)).all()


@router.post("", response_model=DisciplineOut, status_code=status.HTTP_201_CREATED)
def create_discipline(data: DisciplineCreate, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    obj = Discipline(user_id=user.id, name=data.name.strip(), description=data.description)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{discipline_id}", response_model=DisciplineOut)
def get_discipline(discipline_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return get_discipline_or_404(db, discipline_id, user)


@router.patch("/{discipline_id}", response_model=DisciplineOut)
def update_discipline(discipline_id: int, data: DisciplineUpdate,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    obj = get_discipline_or_404(db, discipline_id, user)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(obj, field, value.strip() if field == "name" else value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{discipline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discipline(discipline_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Колоды дисциплины не удаляются — они остаются без дисциплины."""
    db.delete(get_discipline_or_404(db, discipline_id, user))
    db.commit()
