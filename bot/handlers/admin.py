"""Команды администратора: расписание на день и отмена записи."""

from __future__ import annotations

from datetime import timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import Message

from ..config import SERVICES, Settings
from ..db import Database
from ..keyboards import fmt_day
from .client import local_now

router = Router(name="admin")


class IsAdmin(Filter):
    """Фильтр: команды доступны только пользователям из ADMIN_IDS."""

    async def __call__(self, message: Message, settings: Settings) -> bool:
        return message.from_user is not None and message.from_user.id in settings.admin_ids


router.message.filter(IsAdmin())


async def send_schedule(message: Message, db: Database, settings: Settings, days_offset: int) -> None:
    day = local_now(settings).date() + timedelta(days=days_offset)
    bookings = await db.day_bookings(day)
    if not bookings:
        await message.answer(f"На {fmt_day(day)} записей нет.")
        return
    lines = [
        f"<b>{b.starts_at:%H:%M}–{b.ends_at:%H:%M}</b> {escape(SERVICES[b.service].title)}\n"
        f"    {escape(b.client_name)}, {escape(b.phone)} · #{b.id}"
        for b in bookings
    ]
    total = sum(SERVICES[b.service].price for b in bookings)
    await message.answer(
        f"<b>Расписание на {fmt_day(day)}</b>\n\n" + "\n".join(lines) + f"\n\nЗаписей: {len(bookings)}, сумма: {total} ₽"
    )


@router.message(Command("admin"))
async def admin_help(message: Message) -> None:
    await message.answer(
        "<b>Команды администратора</b>\n"
        "/today — записи на сегодня\n"
        "/tomorrow — записи на завтра\n"
        "/cancel_booking N — отменить запись №N (клиент получит уведомление)"
    )


@router.message(Command("today"))
async def today(message: Message, db: Database, settings: Settings) -> None:
    await send_schedule(message, db, settings, 0)


@router.message(Command("tomorrow"))
async def tomorrow(message: Message, db: Database, settings: Settings) -> None:
    await send_schedule(message, db, settings, 1)


@router.message(Command("cancel_booking"), F.text)
async def cancel_booking(message: Message, command: CommandObject, db: Database, bot: Bot) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("Укажите номер записи: /cancel_booking 12")
        return
    booking_id = int(command.args.strip())
    booking = await db.get(booking_id)
    if not booking or not await db.cancel(booking_id):
        await message.answer("Запись не найдена или уже отменена.")
        return
    await message.answer(f"Запись #{booking_id} отменена.")
    service = SERVICES[booking.service]
    await bot.send_message(
        booking.user_id,
        f"К сожалению, ваша запись «{escape(service.title)}» на "
        f"{fmt_day(booking.starts_at.date())} в {booking.starts_at:%H:%M} отменена администратором. "
        "Выберите другое время через «Записаться».",
    )
