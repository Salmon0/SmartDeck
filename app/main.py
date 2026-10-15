from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (регистрация моделей в метаданных)
from app.config import settings
from app.database import Base, engine
from app.routers import auth, cards, decks, demo, disciplines, materials, notifications, stats, study


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="SmartDeck API",
    version="0.1.0",
    description="Бэкенд приложения для обучения по карточкам с интервальным повторением.",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

for module in (auth, disciplines, decks, cards, materials, study, stats, notifications, demo):
    app.include_router(module.router)


@app.get("/health", tags=["service"])
def health():
    return {"status": "ok"}
