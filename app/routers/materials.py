import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user, get_discipline_or_404
from app.models import Deck, Flashcard, StudyMaterial, User
from app.routers.decks import deck_out
from app.schemas import MaterialOut, MaterialUploadOut
from app.services.card_generator import generate_cards
from app.services.document_processor import DocumentProcessingError, detect_format, extract_text

router = APIRouter(prefix="/materials", tags=["materials"])


@router.post("", response_model=MaterialUploadOut, status_code=status.HTTP_201_CREATED,
             summary="Загрузить конспект и получить колоду карточек")
def upload_material(
    file: UploadFile = File(..., description="PDF, DOCX, DOC или MD"),
    title: str | None = Form(default=None, description="Название колоды (по умолчанию — имя файла)"),
    discipline_id: int | None = Form(default=None),
    max_cards: int = Form(default=30, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if discipline_id is not None:
        get_discipline_or_404(db, discipline_id, user)

    file_name = Path(file.filename or "upload").name
    try:
        fmt = detect_format(file_name)
    except DocumentProcessingError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc

    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"Файл больше {settings.max_upload_mb} МБ")

    material = StudyMaterial(user_id=user.id, file_name=file_name, file_format=fmt)
    db.add(material)
    db.flush()

    try:
        text, _ = extract_text(file_name, data)
        drafts, processor = generate_cards(text, max_cards)
        if not drafts:
            raise DocumentProcessingError(
                "Не удалось выделить из текста пары «вопрос — ответ». "
                "Попробуйте конспект с заголовками или определениями вида «Термин — это …».")
    except DocumentProcessingError as exc:
        material.status, material.error = "failed", str(exc)
        db.commit()
        raise HTTPException(422, str(exc)) from exc

    # Сохраняем исходный файл, чтобы материал не терялся (нефункциональное требование).
    target_dir = Path(settings.upload_dir) / str(user.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored = target_dir / f"{uuid.uuid4().hex}.{fmt}"
    stored.write_bytes(data)

    deck = Deck(user_id=user.id, discipline_id=discipline_id,
                title=(title or Path(file_name).stem).strip()[:200] or "Новая колода")
    deck.cards = [Flashcard(question=d.question, answer=d.answer) for d in drafts]
    db.add(deck)
    db.flush()

    material.deck_id = deck.id
    material.stored_path = str(stored)
    material.processor_type = processor
    material.status = "processed"
    db.commit()
    db.refresh(material)
    db.refresh(deck)
    return MaterialUploadOut(material=MaterialOut.model_validate(material),
                             deck=deck_out(db, [deck])[0])


@router.get("", response_model=list[MaterialOut])
def list_materials(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(StudyMaterial).where(StudyMaterial.user_id == user.id)
                      .order_by(StudyMaterial.id.desc())).all()


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Удалить материал (колода остаётся)")
def delete_material(material_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    material = db.get(StudyMaterial, material_id)
    if material is None or material.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Материал не найден(а)")
    if material.stored_path:
        Path(material.stored_path).unlink(missing_ok=True)
    db.delete(material)
    db.commit()
