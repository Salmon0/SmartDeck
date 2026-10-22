# SmartDeck — бэкенд

REST API для приложения обучения по карточкам с интервальным повторением
(курсовая «Основы разработки ПО», ТУСУР). Клиент — Android-приложение (Kotlin + Compose).

**Стек:** Python 3.12, FastAPI, SQLAlchemy 2, SQLite (меняется через `DATABASE_URL`),
Pydantic v2, JWT, pypdf / python-docx, Ollama или OpenAI для генерации карточек.

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
«Термин — это …», «Термин: …» и пары «заголовок → абзац»). Для Ollama задайте
`LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://127.0.0.1:11434` и имя загруженной
модели в `.env`; Ollama должна быть запущена на компьютере с backend. Также можно
выбрать `LLM_PROVIDER=openai` и задать `OPENAI_API_KEY`.
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

## Подключение Supabase PostgreSQL

1. Создайте проект Supabase и выберите регион ближе к большинству пользователей.
2. В панели проекта нажмите **Connect** и выберите **Session pooler**. Для постоянного
   FastAPI backend используйте порт `5432`; строка подключения должна содержать хост
   `*.pooler.supabase.com` и имя пользователя вида `postgres.<PROJECT_REF>`.
3. Скопируйте URI в `DATABASE_URL` в локальном `.env` для разработки или в секреты
   backend-хостинга для развёртывания. Добавьте `sslmode=require`, если его нет.

Пример формата (используйте реальные значения, скопированные из панели Supabase):

```dotenv
DATABASE_URL=postgresql://postgres.PROJECT_REF:DB_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
SECRET_KEY=<длинный случайный секрет>
```

Приложение автоматически выбирает драйвер psycopg 3 для URI `postgres://` и
`postgresql://`. Если пароль содержит зарезервированные URL-символы (`@`, `#`, `?`, `&`
или пробел), закодируйте их в URL. Не отправляйте строку подключения в Android-клиент,
чат или Git: к базе должен подключаться только backend API.

При первом запуске API создаст свои таблицы в новой пустой базе. Не загружайте туда
`smartdeck_dump.sql` из лабораторной: схема этого дампа отличается от моделей backend.
`create_all` создаёт отсутствующие таблицы, но не выполняет миграцию уже существующей
схемы и не переносит данные из локального `smartdeck.db`.

Проверка соединения: `GET /health` возвращает `{"status":"ok"}`, если база доступна,
и HTTP 503, если API не может подключиться. На бесплатном тарифе Supabase база имеет
лимит 500 МБ и проект может приостановиться после недели низкой активности; при
публикации приложения учитывайте эти ограничения.

Загруженные конспекты сейчас сохраняются в `UPLOAD_DIR` на диске backend. При
размещении API на платформе с временным диском настройте постоянный диск или объектное
хранилище: PostgreSQL сохраняет метаданные файла, но не его содержимое.
