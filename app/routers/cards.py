from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_card_or_404, get_current_user, get_deck_or_404
from app.models import Flashcard, User
from app.schemas import CardCreate, CardOut, CardUpdate

router = APIRouter(tags=["cards"])


@router.get("/decks/{deck_id}/cards", response_model=list[CardOut])
def list_cards(deck_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_deck_or_404(db, deck_id, user).cards


@router.post("/decks/{deck_id}/cards", response_model=CardOut, status_code=status.HTTP_201_CREATED)
def add_card(deck_id: int, data: CardCreate, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    deck = get_deck_or_404(db, deck_id, user)
    card = Flashcard(deck_id=deck.id, question=data.question.strip(), answer=data.answer.strip())
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.patch("/cards/{card_id}", response_model=CardOut)
def edit_card(card_id: int, data: CardUpdate, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    card = get_card_or_404(db, card_id, user)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(card, field, value.strip())
    db.commit()
    db.refresh(card)
    return card


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(card_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(get_card_or_404(db, card_id, user))
    db.commit()
