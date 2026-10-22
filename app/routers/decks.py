from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, get_deck_or_404, get_discipline_or_404
from app.models import Deck, Flashcard, User
from app.schemas import DeckCreate, DeckDetail, DeckOut, DeckUpdate
from app.timeutil import utcnow

router = APIRouter(prefix="/decks", tags=["decks"])


def deck_out(db: Session, decks: list[Deck]) -> list[DeckOut]:
    """DeckOut с числом карточек, которые пора повторить (одним запросом)."""
    ids = [d.id for d in decks]
    due = {}
    if ids:
        due = dict(db.execute(
            select(Flashcard.deck_id, func.count(Flashcard.id))
            .where(Flashcard.deck_id.in_(ids), Flashcard.next_review <= utcnow())
            .group_by(Flashcard.deck_id)).all())
    out = []
    for d in decks:
        item = DeckOut.model_validate(d)
        item.due_count = due.get(d.id, 0)
        out.append(item)
    return out


@router.get("", response_model=list[DeckOut])
def list_decks(discipline_id: int | None = Query(default=None, description="Фильтр по дисциплине"),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(Deck).where(Deck.user_id == user.id).order_by(Deck.created_at.desc(), Deck.id.desc())
    if discipline_id is not None:
        query = query.where(Deck.discipline_id == discipline_id)
    return deck_out(db, list(db.scalars(query).all()))


@router.post("", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
def create_deck(data: DeckCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if data.discipline_id is not None:
        get_discipline_or_404(db, data.discipline_id, user)
    deck = Deck(user_id=user.id, title=data.title.strip(), discipline_id=data.discipline_id)
    db.add(deck)
    db.commit()
    db.refresh(deck)
    return deck_out(db, [deck])[0]


@router.get("/{deck_id}", response_model=DeckDetail)
def get_deck(deck_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    deck = get_deck_or_404(db, deck_id, user)
    base = deck_out(db, [deck])[0]
    return DeckDetail(**base.model_dump(), cards=deck.cards)


@router.patch("/{deck_id}", response_model=DeckOut)
def update_deck(deck_id: int, data: DeckUpdate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    deck = get_deck_or_404(db, deck_id, user)
    changes = data.model_dump(exclude_unset=True)
    if "title" in changes and changes["title"] is not None:
        deck.title = changes["title"].strip()
    if "discipline_id" in changes:
        if changes["discipline_id"] is not None:
            get_discipline_or_404(db, changes["discipline_id"], user)
        deck.discipline_id = changes["discipline_id"]
    db.commit()
    db.refresh(deck)
    return deck_out(db, [deck])[0]


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_deck_or_404(db, deck_id, user))
    db.commit()
