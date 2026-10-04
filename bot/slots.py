"""Расчёт свободных слотов для записи. Чистая логика без Telegram и БД."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .config import SLOT_STEP_MIN, WORK_END_HOUR, WORK_START_HOUR

Interval = tuple[datetime, datetime]


def overlaps(a: Interval, b: Interval) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def free_slots(day: date, duration: int, busy: list[Interval], now: datetime) -> list[datetime]:
    """Начала всех слотов дня, куда помещается услуга длительностью duration минут.

    Слот подходит, если он в будущем, услуга заканчивается до конца рабочего дня
    и не пересекается с уже занятыми интервалами.
    """
    start = datetime.combine(day, time(WORK_START_HOUR))
    day_end = datetime.combine(day, time(WORK_END_HOUR))
    length = timedelta(minutes=duration)
    step = timedelta(minutes=SLOT_STEP_MIN)

    slots = []
    while start + length <= day_end:
        candidate = (start, start + length)
        if start > now and not any(overlaps(candidate, b) for b in busy):
            slots.append(start)
        start += step
    return slots


def upcoming_days(today: date, days_ahead: int) -> list[date]:
    return [today + timedelta(days=i) for i in range(days_ahead)]
