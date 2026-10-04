from datetime import date, datetime, timedelta

import pytest

from bot.db import Database, SlotTakenError

START = datetime(2030, 1, 10, 12, 0)


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init()
    return database


async def make(db, user_id=1, start=START, minutes=60):
    return await db.create(user_id, "Иван", "+79001234567", "haircut", start, start + timedelta(minutes=minutes))


async def test_create_and_busy(db):
    booking = await make(db)
    assert booking.id == 1
    assert await db.busy_intervals(date(2030, 1, 10)) == [(START, START + timedelta(hours=1))]


async def test_overlapping_booking_rejected(db):
    await make(db)
    with pytest.raises(SlotTakenError):
        await make(db, user_id=2, start=START + timedelta(minutes=30))
    # впритык — можно
    await make(db, user_id=2, start=START + timedelta(hours=1))


async def test_cancel_frees_slot_and_checks_owner(db):
    booking = await make(db, user_id=1)
    assert not await db.cancel(booking.id, user_id=2)  # чужую запись отменить нельзя
    assert await db.cancel(booking.id, user_id=1)
    assert await db.busy_intervals(date(2030, 1, 10)) == []
    await make(db, user_id=2)  # слот снова свободен


async def test_due_reminders_sent_once(db):
    booking = await make(db)
    now = START - timedelta(hours=1)
    due = await db.due_reminders(now, timedelta(hours=2))
    assert [b.id for b in due] == [booking.id]
    await db.mark_reminded(booking.id)
    assert await db.due_reminders(now, timedelta(hours=2)) == []


async def test_reminder_not_due_too_early(db):
    await make(db)
    assert await db.due_reminders(START - timedelta(hours=5), timedelta(hours=2)) == []
