import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="smartdeck-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/storage"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"
os.environ["OPENAI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


def register(client, name="vlad", email="vlad@example.com", password="secret123"):
    r = client.post("/auth/register", json={"email": email, "username": name, "password": password})
    assert r.status_code == 201, r.text
    token = client.post("/auth/login", json={"login": name, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth(client):
    return register(client)


NOTES_MD = """# Интервальное обучение

Интервальное обучение — методика повторения материала через увеличивающиеся интервалы времени.
Зубрёжка: многократное повторение информации за короткий срок без пауз.

# Карточки

Карточка состоит из вопроса и ответа. Они помогают тренировать активное вспоминание материала.

- Алгоритм SM-2 — алгоритм планирования повторений, использующий коэффициент лёгкости.
"""
