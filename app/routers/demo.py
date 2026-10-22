"""Демонстрационная колода для незарегистрированного пользователя (класс Guest)."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoCard(BaseModel):
    question: str
    answer: str


class DemoDeck(BaseModel):
    title: str
    cards: list[DemoCard]


_DEMO = DemoDeck(
    title="Демо: интервальное обучение",
    cards=[
        DemoCard(question="Что такое интервальное повторение?",
                 answer="Методика, при которой материал повторяют через увеличивающиеся интервалы времени."),
        DemoCard(question="Чем интервальное повторение отличается от зубрёжки?",
                 answer="Повторения более редкие, но своевременные, а не многократные за короткий срок."),
        DemoCard(question="Как меняется интервал после верного ответа?",
                 answer="Увеличивается: например, 1 день, затем 6 дней, затем интервал умножается на коэффициент."),
        DemoCard(question="Что происходит с карточкой после неверного ответа?",
                 answer="Она возвращается в повторение и показывается чаще."),
        DemoCard(question="Зачем нужны карточки вопрос — ответ?",
                 answer="Они заставляют вспоминать информацию, а не просто перечитывать конспект."),
    ],
)


@router.get("/deck", response_model=DemoDeck, summary="Демо-колода без авторизации")
def demo_deck():
    return _DEMO
