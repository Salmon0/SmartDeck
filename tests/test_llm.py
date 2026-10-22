import json

import httpx
import pytest

from app.config import settings
from app.services import card_generator as cg
from tests.conftest import NOTES_MD


def ollama_reply(cards):
    return {"message": {"content": json.dumps({"cards": cards}, ensure_ascii=False)}}


@pytest.fixture()
def ollama(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")


def test_provider_selection(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "llm_provider", "auto")
    assert cg.active_provider() == "heuristic"
    monkeypatch.setattr(settings, "openai_api_key", "k")
    assert cg.active_provider() == "openai"
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    assert cg.active_provider() == "ollama"
    monkeypatch.setattr(settings, "llm_provider", "heuristic")
    assert cg.active_provider() == "heuristic"


def test_parse_cards_is_tolerant():
    ok = [{"question": "Q1", "answer": "A1"}]
    assert cg.parse_cards(json.dumps({"cards": ok}))[0].question == "Q1"
    assert cg.parse_cards("```json\n" + json.dumps({"cards": ok}) + "\n```")[0].answer == "A1"
    assert cg.parse_cards(json.dumps(ok))[0].question == "Q1"                       # список без обёртки
    assert cg.parse_cards(json.dumps({"flashcards": ok}))[0].question == "Q1"       # другое имя ключа
    assert cg.parse_cards(json.dumps(ok[0]))[0].question == "Q1"                    # одна карточка
    assert cg.parse_cards(json.dumps([{"вопрос": "В", "ответ": "О"}]))[0].answer == "О"
    junk = [{"question": "", "answer": "x"}, {"question": 5, "answer": "x"}, "text", {"q": 1}]
    assert cg.parse_cards(json.dumps(junk)) == []
    with pytest.raises(json.JSONDecodeError):
        cg.parse_cards("не json")


def test_ollama_used_and_payload(monkeypatch, ollama):
    seen = {}

    def fake_post(url, headers, payload, timeout):
        seen.update(url=url, payload=payload, timeout=timeout)
        return ollama_reply([{"question": "Что такое SM-2?", "answer": "Алгоритм повторений."}])

    monkeypatch.setattr(cg, "_post_json", fake_post)
    cards, provider = cg.generate_cards(NOTES_MD, 5)
    assert provider == "ollama" and cards[0].question == "Что такое SM-2?"
    assert seen["url"].endswith("/api/chat")
    assert seen["payload"]["format"] == "json" and seen["payload"]["stream"] is False
    assert seen["payload"]["options"]["num_ctx"] == settings.ollama_num_ctx
    assert seen["payload"]["model"] == settings.ollama_model


def test_fallback_when_ollama_is_down(monkeypatch, ollama):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(cg, "_post_json", boom)
    cards, provider = cg.generate_cards(NOTES_MD, 10)
    assert provider == "heuristic" and cards


def test_fallback_when_model_returns_garbage(monkeypatch, ollama):
    monkeypatch.setattr(cg, "_post_json", lambda *a, **k: {"message": {"content": "извините, не могу"}})
    cards, provider = cg.generate_cards(NOTES_MD, 10)
    assert provider == "heuristic" and cards


def test_one_bad_chunk_does_not_lose_document(monkeypatch, ollama):
    text = "\n\n".join(f"Абзац номер {i}. " + "слово " * 300 for i in range(6))
    assert len(cg.split_chunks(text, cg.OLLAMA_CHUNK)) >= 3
    calls = {"n": 0}

    def flaky(url, headers, payload, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"message": {"content": "мусор"}}
        return ollama_reply([{"question": f"Вопрос {calls['n']}", "answer": "Ответ"}])

    monkeypatch.setattr(cg, "_post_json", flaky)
    cards, provider = cg.generate_cards(text, 10)
    assert provider == "ollama" and len(cards) >= 2


def test_upload_reports_ollama_processor(client, auth, monkeypatch, ollama):
    monkeypatch.setattr(cg, "_post_json", lambda *a, **k: ollama_reply(
        [{"question": "Что такое колода?", "answer": "Набор карточек."}]))
    r = client.post("/materials", headers=auth,
                    files={"file": ("n.md", NOTES_MD.encode(), "text/markdown")})
    assert r.status_code == 201, r.text
    assert r.json()["material"]["processor_type"] == "ollama"
    assert r.json()["deck"]["card_count"] == 1


def test_local_requests_ignore_system_proxy(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, **kwargs):
            seen.setdefault("trust_env", []).append(kwargs["trust_env"])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers, json):
            return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(cg.httpx, "Client", FakeClient)
    cg._post_json("http://localhost:11434/api/chat", {}, {}, 5)
    cg._post_json("http://127.0.0.1:11434/api/chat", {}, {}, 5)
    cg._post_json("https://api.openai.com/v1/chat/completions", {}, {}, 5)
    assert seen["trust_env"] == [False, False, True]
