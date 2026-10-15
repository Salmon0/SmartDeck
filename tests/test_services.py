from datetime import timedelta

from app.models import Flashcard
from app.services.card_generator import heuristic_cards, split_chunks
from app.services.document_processor import DocumentProcessingError, detect_format, extract_text
from app.services.scheduler import apply_review
from app.timeutil import utcnow
import pytest

from tests.conftest import NOTES_MD


def new_card():
    return Flashcard(question="q", answer="a", interval_days=0, ease=2.5, repetitions=0,
                     correct_count=0, wrong_count=0, next_review=utcnow())


def test_sm2_intervals_grow():
    card, now = new_card(), utcnow()
    apply_review(card, True, now=now)
    assert card.interval_days == 1
    apply_review(card, True, now=now)
    assert card.interval_days == 6
    apply_review(card, True, now=now)
    assert card.interval_days > 6
    assert card.next_review > now + timedelta(days=6)
    assert card.correct_count == 3


def test_sm2_wrong_resets_and_requeues():
    card, now = new_card(), utcnow()
    apply_review(card, True, now=now)
    apply_review(card, False, now=now)
    assert card.repetitions == 0 and card.interval_days == 0
    assert card.next_review == now
    assert card.wrong_count == 1
    assert card.ease >= 1.3


def test_quality_cannot_contradict_correctness():
    card = new_card()
    assert apply_review(card, True, quality=0) == 3
    assert apply_review(card, False, quality=5) == 2


def test_heuristic_generator_finds_definitions_and_headings():
    cards = heuristic_cards(NOTES_MD, 20)
    questions = [c.question for c in cards]
    assert "Что такое Интервальное обучение?" in questions
    assert "Что такое Алгоритм SM-2?" in questions
    assert any("Карточки" in q for q in questions)
    assert len(questions) == len(set(questions))


def test_heuristic_respects_limit_and_english():
    text = "Photosynthesis — the process by which plants convert light into energy.\n" * 1
    text += "Chlorophyll — the green pigment that absorbs sunlight in plants.\n"
    cards = heuristic_cards(text, 1)
    assert len(cards) == 1 and cards[0].question.startswith("What is")


def test_split_chunks_limits_size():
    text = "\n\n".join(["абзац " * 100] * 30)
    chunks = split_chunks(text, size=1000)
    assert chunks and all(len(c) <= 2000 for c in chunks)


def test_document_processor_formats():
    assert detect_format("a.MD") == "md" and detect_format("b.markdown") == "md"
    with pytest.raises(DocumentProcessingError):
        detect_format("c.exe")
    text, fmt = extract_text("n.md", NOTES_MD.encode("cp1251"))
    assert fmt == "md" and "Интервальное" in text
    with pytest.raises(DocumentProcessingError):
        extract_text("empty.md", b"  ")
