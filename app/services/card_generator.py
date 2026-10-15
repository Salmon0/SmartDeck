"""Генерация карточек «вопрос — ответ» из текста конспекта.

Основной путь — OpenAI API (как в таблице 2.2 курсовой). Если ключа нет или запрос
не удался, используется эвристический генератор: определения («Термин — это …»,
«Термин: …») и пары «заголовок → первый абзац».
"""
import json
import logging
import re
from dataclasses import dataclass

import httpx

from app.config import settings

log = logging.getLogger(__name__)

CHUNK_SIZE = 3500
MAX_CHUNKS = 15


@dataclass
class CardDraft:
    question: str
    answer: str


# ---------------- публичный API ----------------
def generate_cards(text: str, max_cards: int) -> tuple[list[CardDraft], str]:
    """Возвращает (карточки, тип обработчика: 'openai' | 'heuristic')."""
    max_cards = max(1, min(max_cards, settings.max_cards_per_material))
    if settings.openai_api_key:
        try:
            cards = _openai_cards(text, max_cards)
            if cards:
                return cards, "openai"
        except Exception as exc:  # сеть, лимиты, невалидный JSON — переходим на запасной путь
            log.warning("OpenAI generation failed, using heuristic: %s", exc)
    return heuristic_cards(text, max_cards), "heuristic"


# ---------------- OpenAI ----------------
_SYSTEM = (
    "Ты помогаешь студенту готовиться к экзамену. По фрагменту конспекта составь карточки "
    "«вопрос — ответ» на том же языке, что и текст. Вопрос — конкретный и самодостаточный, "
    "ответ — краткий (1–3 предложения) и строго по тексту. Не выдумывай факты. "
    'Верни только JSON вида {"cards":[{"question":"...","answer":"..."}]}.'
)


def split_chunks(text: str, size: int = CHUNK_SIZE) -> list[str]:
    chunks, current = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if current and len(current) + len(para) + 2 > size:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{para}".strip()
        while len(current) > size * 2:  # очень длинный абзац
            chunks.append(current[:size])
            current = current[size:]
    if current:
        chunks.append(current)
    return chunks[:MAX_CHUNKS]


def _openai_cards(text: str, max_cards: int) -> list[CardDraft]:
    chunks = split_chunks(text)
    per_chunk = max(2, -(-max_cards // max(1, len(chunks))))
    result: list[CardDraft] = []
    with httpx.Client(timeout=60) as client:
        for chunk in chunks:
            if len(result) >= max_cards:
                break
            resp = client.post(
                f"{settings.openai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user",
                         "content": f"Создай не более {per_chunk} карточек.\n\nКонспект:\n{chunk}"},
                    ],
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            for item in json.loads(content).get("cards", []):
                q, a = item.get("question"), item.get("answer")
                if isinstance(q, str) and isinstance(a, str) and q.strip() and a.strip():
                    result.append(CardDraft(q.strip()[:2000], a.strip()[:5000]))
    return _dedupe(result)[:max_cards]


# ---------------- эвристика ----------------
_CYR = re.compile(r"[А-Яа-яЁё]")
_LAT = re.compile(r"[A-Za-z]")
_BULLET = re.compile(r"^\s*(?:[-*•–]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s+(?P<t>.+?)\s*#*\s*$")
_DEF_DASH = re.compile(r"^(?P<term>[^:—–]{2,80}?)\s+[—–-]\s+(?P<defn>\S.{9,})$")
_DEF_COLON = re.compile(r"^(?P<term>[^:]{2,60}):\s+(?P<defn>\S.{9,})$")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZА-ЯЁ«\"])")


def _clean(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[*_`]+", "", s)
    return s.strip()


def _valid_term(term: str) -> bool:
    return (
        1 <= len(term.split()) <= 6
        and not re.search(r"[.!?;]", term)
        and not term[0].isdigit()
    )


def _dedupe(cards: list[CardDraft]) -> list[CardDraft]:
    seen, out = set(), []
    for c in cards:
        key = c.question.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def heuristic_cards(text: str, max_cards: int) -> list[CardDraft]:
    ru = len(_CYR.findall(text)) >= len(_LAT.findall(text))
    q_def = "Что такое {}?" if ru else "What is {}?"
    q_head = "Что важно знать по теме «{}»?" if ru else "What are the key points of “{}”?"

    cards: list[CardDraft] = []
    heading: str | None = None
    paragraph: list[str] = []

    def flush_heading():
        nonlocal paragraph
        body = " ".join(paragraph).strip()
        if heading and len(body) >= 40:
            cards.append(CardDraft(q_head.format(heading), body[:400].rstrip()))
        paragraph = []

    for raw in text.split("\n"):
        line = raw.strip()
        m = _HEADING.match(line)
        if m:
            flush_heading()
            heading = _clean(m.group("t"))
            continue
        if not line:
            if paragraph:
                flush_heading()
                heading = None
            continue
        line = _clean(_BULLET.sub("", line))
        if heading is not None:
            paragraph.append(line)
        for sentence in _SENT_SPLIT.split(line):
            sentence = sentence.strip()
            match = _DEF_DASH.match(sentence) or _DEF_COLON.match(sentence)
            if match and _valid_term(match.group("term").strip()):
                term = match.group("term").strip()
                defn = re.sub(r"^(это|является|—|–)\s+", "", match.group("defn").strip(), flags=re.I)
                cards.append(CardDraft(q_def.format(term), defn[:400]))
    flush_heading()
    return _dedupe(cards)[:max_cards]
