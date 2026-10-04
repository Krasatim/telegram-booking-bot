"""Точка входа: python -m bot"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .config import load_settings
from .db import Database
from .handlers import admin, client
from .reminders import reminders_loop


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()

    db = Database(settings.db_path)
    await db.init()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # db и settings пробрасываются в обработчики как аргументы
    dp = Dispatcher(db=db, settings=settings)
    dp.include_routers(admin.router, client.router)

    await bot.set_my_commands([BotCommand(command="start", description="Главное меню")])
    reminders = asyncio.create_task(reminders_loop(bot, db, settings))
    try:
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
