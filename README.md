# SmartDeck — бэкенд

REST API для приложения обучения по карточкам с интервальным повторением
(курсовая «Основы разработки ПО», ТУСУР). Клиент — Android-приложение (Kotlin + Compose).

**Стек:** Python 3.12, FastAPI, SQLAlchemy 2, SQLite (меняется через `DATABASE_URL`),
Pydantic v2, JWT, pypdf / python-docx, OpenAI API (необязательно).

## Запуск (Windows / PyCharm)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
uvicorn app.main:app --reload
```

- Swagger: http://127.0.0.1:8000/docs (кнопка **Authorize** — логин/пароль)
- Из Android-эмулятора сервер доступен по `http://10.0.2.2:8000`
- Тесты: `pytest`
- Docker: `docker build -t smartdeck . && docker run -p 8000:8000 smartdeck`

Без `OPENAI_API_KEY` карточки строит эвристический генератор (определения
«Термин — это …», «Термин: …» и пары «заголовок → абзац»). С ключом — OpenAI,
а при ошибке API автоматически включается эвристика.

## Соответствие курсовой

| Требование (п. 1.4) | Эндпоинты |
|---|---|
| Регистрация и вход; демо-колода для гостя | `POST /auth/register`, `POST /auth/login`, `GET /auth/me`, `DELETE /auth/me`, `GET /demo/deck` |
| Загрузка PDF / DOCX / DOC / MD → колода | `POST /materials` (multipart: `file`, `title`, `discipline_id`, `max_cards`) |
| Колоды и карточки: просмотр, правка, добавление, удаление | `/decks`, `/decks/{id}/cards`, `/cards/{id}` |
| Дисциплины и фильтрация | `/disciplines`, `GET /decks?discipline_id=` |
| Учебные сессии | `POST /decks/{id}/sessions`, `GET /sessions/{id}/next`, `POST /sessions/{id}/answers`, `POST /sessions/{id}/finish` |
| Частота повторения (SM-2) | `app/services/scheduler.py` |
| Статистика (до первой сессии `has_data=false`) | `GET /stats/overview` |
| Недельный отчёт | `GET /stats/weekly?day=YYYY-MM-DD` |
| Напоминания | `GET/PUT /notifications`, `GET /notifications/reminder` |

## Как клиент проводит сессию

1. `POST /decks/{id}/sessions` → `session.id`
2. `GET /sessions/{id}/next` → `card` (или `null`, если повторять нечего)
3. Пользователь отвечает → `POST /sessions/{id}/answers` с `{card_id, is_correct, response_time_ms}`;
   необязательное `quality` 0–5 уточняет оценку по шкале SM-2
4. Повторять шаги 2–3, затем `POST /sessions/{id}/finish`

Неверно отвеченная карточка возвращается в той же сессии после одной другой карточки.
Верная — откладывается на 1 → 6 → `interval × ease` дней.

## Структура

```
app/
  main.py  config.py  database.py  models.py  schemas.py  security.py  deps.py
  routers/   auth, disciplines, decks, cards, materials, study, stats, notifications, demo
  services/  document_processor.py  card_generator.py  scheduler.py  statistics.py
tests/       pytest (сервисы + API-сценарии)
```

Сервисы соответствуют сервисным классам из UML: `DocumentProcessor`, `StudyScheduler`, `Statistics`.

## Отличия от документа и допущения

- Класс `Guest` в БД не хранится (п. 3.1.4): гость — это неавторизованный запрос, ему доступен `/demo/deck`.
- В п. 3.2.1 перечислено 7 таблиц, но в спецификации данных (п. 2.3) есть ещё дисциплины, сессии и результаты ответов,
  без которых не работают статистика и недельный отчёт. Поэтому таблиц 8:
  `users, disciplines, decks, flashcards, study_materials, notification_settings, study_sessions, study_results`.
  Данные «обработчика документов» (тип, статус) хранятся в `study_materials`.
- Ссылка на дисциплину у колоды необязательна; при удалении дисциплины колоды остаются без неё.
- «Время обучения» в отчёте — сумма времени ответов (`response_time_ms`), то есть именно активное обучение.
- Пароли — PBKDF2-SHA256 с солью; токен — JWT (HS256), срок по умолчанию 7 дней.
- `.doc` читается через `antiword` или LibreOffice (если установлены); иначе API просит загрузить `.docx`.
- Схема БД создаётся при старте (`create_all`). Для дальнейшей эволюции схемы стоит подключить Alembic.
