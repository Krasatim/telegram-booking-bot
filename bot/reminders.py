"""Фоновая задача: напоминает клиентам о визите."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from html import escape

from aiogram import Bot

from .config import SERVICES, Settings
from .db import Database
from .handlers.client import local_now

log = logging.getLogger(__name__)
CHECK_INTERVAL_SEC = 60


async def send_due_reminders(bot: Bot, db: Database, settings: Settings) -> int:
    due = await db.due_reminders(local_now(settings), timedelta(hours=settings.remind_before_hours))
    for booking in due:
        service = SERVICES[booking.service]
        try:
            await bot.send_message(
                booking.user_id,
                f"⏰ Напоминаем: сегодня в <b>{booking.starts_at:%H:%M}</b> — {escape(service.title)}.\n"
                "Если планы изменились, отмените запись в разделе «Мои записи».",
            )
        except Exception as exc:  # клиент мог заблокировать бота
            log.warning("Не удалось отправить напоминание по записи #%s: %s", booking.id, exc)
        await db.mark_reminded(booking.id)
    return len(due)


async def reminders_loop(bot: Bot, db: Database, settings: Settings) -> None:
    while True:
        try:
            await send_due_reminders(bot, db, settings)
        except Exception:
            log.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(CHECK_INTERVAL_SEC)
