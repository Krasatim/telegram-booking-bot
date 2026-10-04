from datetime import date, datetime

from bot.slots import free_slots

DAY = date(2030, 1, 10)
MORNING = datetime(2030, 1, 10, 8, 0)


def test_full_day_has_all_slots():
    slots = free_slots(DAY, 60, busy=[], now=MORNING)
    assert slots[0] == datetime(2030, 1, 10, 10, 0)
    # последняя часовая услуга должна закончиться к 20:00
    assert slots[-1] == datetime(2030, 1, 10, 19, 0)
    assert len(slots) == 19  # 10:00..19:00 с шагом 30 минут


def test_busy_interval_blocks_overlapping_slots():
    busy = [(datetime(2030, 1, 10, 12, 0), datetime(2030, 1, 10, 13, 0))]
    slots = free_slots(DAY, 60, busy=busy, now=MORNING)
    assert datetime(2030, 1, 10, 11, 0) in slots  # заканчивается ровно в 12:00
    assert datetime(2030, 1, 10, 11, 30) not in slots
    assert datetime(2030, 1, 10, 12, 30) not in slots
    assert datetime(2030, 1, 10, 13, 0) in slots


def test_past_slots_are_hidden():
    now = datetime(2030, 1, 10, 15, 10)
    slots = free_slots(DAY, 30, busy=[], now=now)
    assert slots[0] == datetime(2030, 1, 10, 15, 30)


def test_long_service_does_not_fit_after_hours():
    slots = free_slots(DAY, 90, busy=[], now=MORNING)
    assert slots[-1] == datetime(2030, 1, 10, 18, 30)
