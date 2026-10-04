"""Сквозной тест: прогоняем реальные апдейты Telegram через диспетчер без сети."""

from datetime import datetime, timedelta
from itertools import count

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import SendMessage

from bot.config import Settings
from bot.db import Database
from bot.handlers import admin, client
from bot.handlers.client import local_now
from bot.keyboards import BTN_BOOK, ConfirmCB, DayCB, ServiceCB, TimeCB

USER_ID = 100
ADMIN_ID = 999
_ids = count(1)


class FakeBot(Bot):
    """Бот, который не ходит в сеть, а запоминает вызванные методы API."""

    def __init__(self):
        super().__init__("42:TEST", default=DefaultBotProperties(parse_mode="HTML"))
        self.calls = []

    async def __call__(self, method, request_timeout=None):
        self.calls.append(method)
        return True

    def sent_to(self, chat_id):
        return [c.text for c in self.calls if isinstance(c, SendMessage) and c.chat_id == chat_id]


def user(uid):
    return {"id": uid, "is_bot": False, "first_name": "Test"}


def message_update(uid, text=None, contact=None):
    msg = {"message_id": next(_ids), "date": 0, "chat": {"id": uid, "type": "private"}, "from": user(uid)}
    if text is not None:
        msg["text"] = text
        if text.startswith("/"):
            msg["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    if contact:
        msg["contact"] = {"phone_number": contact, "first_name": "Test", "user_id": uid}
    return {"update_id": next(_ids), "message": msg}


def callback_update(uid, data):
    return {
        "update_id": next(_ids),
        "callback_query": {
            "id": str(next(_ids)),
            "from": user(uid),
            "chat_instance": "test",
            "data": data,
            "message": {
                "message_id": next(_ids),
                "date": 0,
                "chat": {"id": uid, "type": "private"},
                "from": {"id": 42, "is_bot": True, "first_name": "Bot"},
                "text": "…",
            },
        },
    }


@pytest.fixture
async def env(tmp_path):
    settings = Settings(bot_token="42:TEST", admin_ids=frozenset({ADMIN_ID}), db_path=str(tmp_path / "t.db"))
    db = Database(settings.db_path)
    await db.init()
    dp = Dispatcher(db=db, settings=settings)
    # роутеры — модульные синглтоны, поэтому для каждого теста отвязываем их от прошлого диспетчера
    for r in (admin.router, client.router):
        r._parent_router = None
    dp.include_routers(admin.router, client.router)
    return dp, FakeBot(), db, settings


async def test_full_booking_flow(env):
    dp, bot, db, settings = env
    tomorrow = local_now(settings).date() + timedelta(days=1)
    slot = datetime.combine(tomorrow, datetime.min.time()).replace(hour=12)

    for update in (
        message_update(USER_ID, "/start"),
        message_update(USER_ID, BTN_BOOK),
        callback_update(USER_ID, ServiceCB(code="haircut").pack()),
        callback_update(USER_ID, DayCB(code="haircut", day=f"{tomorrow:%Y%m%d}").pack()),
        callback_update(USER_ID, TimeCB(code="haircut", at=f"{slot:%Y%m%d%H%M}").pack()),
        message_update(USER_ID, "Иван"),
        message_update(USER_ID, contact="79001234567"),
        callback_update(USER_ID, ConfirmCB(ok=True).pack()),
    ):
        await dp.feed_raw_update(bot, update)

    bookings = await db.user_upcoming(USER_ID, local_now(settings))
    assert len(bookings) == 1
    assert bookings[0].starts_at == slot
    assert bookings[0].client_name == "Иван"
    assert bookings[0].phone == "+79001234567"
    assert any("Новая запись" in t for t in bot.sent_to(ADMIN_ID))


async def test_invalid_phone_is_rejected(env):
    dp, bot, db, settings = env
    tomorrow = local_now(settings).date() + timedelta(days=1)
    slot = datetime.combine(tomorrow, datetime.min.time()).replace(hour=15)
    await dp.feed_raw_update(bot, callback_update(USER_ID, TimeCB(code="beard", at=f"{slot:%Y%m%d%H%M}").pack()))
    await dp.feed_raw_update(bot, message_update(USER_ID, "Пётр"))
    await dp.feed_raw_update(bot, message_update(USER_ID, "позвоните мне"))
    assert any("Не похоже на номер" in t for t in bot.sent_to(USER_ID))


async def test_admin_commands_only_for_admins(env):
    dp, bot, db, settings = env
    await dp.feed_raw_update(bot, message_update(USER_ID, "/today"))
    assert bot.sent_to(USER_ID) == []  # обычный пользователь — тишина
    await dp.feed_raw_update(bot, message_update(ADMIN_ID, "/today"))
    assert any("записей нет" in t for t in bot.sent_to(ADMIN_ID))
