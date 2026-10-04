"""Настройки бота: услуги, рабочее время и параметры из .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


@dataclass(frozen=True)
class Service:
    code: str
    title: str
    duration: int  # минуты
    price: int  # рубли


# Услуги заведения — правятся под конкретного клиента
SERVICES: dict[str, Service] = {
    s.code: s
    for s in (
        Service("haircut", "Мужская стрижка", 60, 1200),
        Service("beard", "Оформление бороды", 30, 700),
        Service("combo", "Стрижка + борода", 90, 1700),
    )
}

WORK_START_HOUR = 10  # первый слот
WORK_END_HOUR = 20  # к этому времени услуга должна закончиться
SLOT_STEP_MIN = 30  # шаг сетки записи
DAYS_AHEAD = 7  # на сколько дней вперёд можно записаться


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int] = field(default_factory=frozenset)
    db_path: str = "bookings.db"
    timezone: ZoneInfo = ZoneInfo("Europe/Moscow")
    remind_before_hours: int = 2


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("Не задан BOT_TOKEN — скопируйте .env.example в .env и впишите токен")
    admins = frozenset(int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip())
    return Settings(
        bot_token=token,
        admin_ids=admins,
        db_path=os.getenv("DB_PATH", "bookings.db"),
        timezone=ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow")),
        remind_before_hours=int(os.getenv("REMIND_BEFORE_HOURS", "2")),
    )
