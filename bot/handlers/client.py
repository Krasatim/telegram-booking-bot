"""Сценарий клиента: выбор услуги, даты, времени, ввод контактов, подтверждение."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..config import DAYS_AHEAD, SERVICES, Settings
from ..db import Booking, Database, SlotTakenError
from ..keyboards import (
    BTN_BOOK,
    BTN_MY,
    BTN_PRICES,
    BackCB,
    CancelCB,
    ConfirmCB,
    DayCB,
    ServiceCB,
    TimeCB,
    confirm_kb,
    contact_keyboard,
    days_kb,
    fmt_day,
    fmt_dt,
    main_menu,
    my_bookings_kb,
    services_kb,
    times_kb,
)
from ..slots import free_slots, upcoming_days

router = Router(name="client")
log = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^\+?[\d\s\-()]{10,18}$")


class BookingForm(StatesGroup):
    name = State()
    phone = State()
    confirm = State()


def local_now(settings: Settings) -> datetime:
    """Текущее время заведения без часового пояса — в таком виде хранятся записи."""
    return datetime.now(settings.timezone).replace(tzinfo=None)


async def notify_admins(bot: Bot, settings: Settings, text: str) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:  # админ мог не запускать бота — не роняем сценарий клиента
            log.warning("Не удалось уведомить админа %s: %s", admin_id, exc)


def booking_text(b: Booking) -> str:
    s = SERVICES[b.service]
    return (
        f"<b>{escape(s.title)}</b> — {fmt_dt(b.starts_at)}\n"
        f"Клиент: {escape(b.client_name)}, {escape(b.phone)}\n"
        f"Стоимость: {s.price} ₽"
    )


# --- Главное меню ---------------------------------------------------------


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Здравствуйте! Я помогу записаться в барбершоп.\nВыберите действие в меню ниже 👇",
        reply_markup=main_menu(),
    )


@router.message(F.text == BTN_PRICES)
async def prices(message: Message) -> None:
    lines = [f"• {escape(s.title)} — {s.price} ₽ ({s.duration} мин)" for s in SERVICES.values()]
    await message.answer("<b>Услуги и цены</b>\n\n" + "\n".join(lines))


@router.message(F.text == BTN_BOOK)
async def book(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Выберите услугу:", reply_markup=services_kb())


# --- Выбор услуги, даты и времени -----------------------------------------


async def show_days(callback: CallbackQuery, code: str, db: Database, settings: Settings) -> None:
    now = local_now(settings)
    duration = SERVICES[code].duration
    days = []
    for day in upcoming_days(now.date(), DAYS_AHEAD):
        if free_slots(day, duration, await db.busy_intervals(day), now):
            days.append(day)
    if not days:
        await callback.message.edit_text("К сожалению, на ближайшую неделю свободного времени нет.")
        return
    await callback.message.edit_text(
        f"<b>{escape(SERVICES[code].title)}</b>\nВыберите день:", reply_markup=days_kb(code, days)
    )


@router.callback_query(ServiceCB.filter())
async def on_service(callback: CallbackQuery, callback_data: ServiceCB, db: Database, settings: Settings) -> None:
    await show_days(callback, callback_data.code, db, settings)
    await callback.answer()


@router.callback_query(DayCB.filter())
async def on_day(callback: CallbackQuery, callback_data: DayCB, db: Database, settings: Settings) -> None:
    day = datetime.strptime(callback_data.day, "%Y%m%d").date()
    service = SERVICES[callback_data.code]
    slots = free_slots(day, service.duration, await db.busy_intervals(day), local_now(settings))
    if not slots:
        await callback.answer("На этот день всё занято, выберите другой", show_alert=True)
        return
    await callback.message.edit_text(
        f"<b>{escape(service.title)}</b>, {fmt_day(day)}\nВыберите время:",
        reply_markup=times_kb(callback_data.code, slots),
    )
    await callback.answer()


@router.callback_query(BackCB.filter())
async def on_back(callback: CallbackQuery, callback_data: BackCB, db: Database, settings: Settings) -> None:
    if callback_data.to == "days":
        await show_days(callback, callback_data.code, db, settings)
    else:
        await callback.message.edit_text("Выберите услугу:", reply_markup=services_kb())
    await callback.answer()


@router.callback_query(TimeCB.filter())
async def on_time(callback: CallbackQuery, callback_data: TimeCB, state: FSMContext) -> None:
    await state.update_data(code=callback_data.code, at=callback_data.at)
    await state.set_state(BookingForm.name)
    starts = datetime.strptime(callback_data.at, "%Y%m%d%H%M")
    await callback.message.edit_text(
        f"<b>{escape(SERVICES[callback_data.code].title)}</b> — {fmt_dt(starts)}\n\nКак к вам обращаться?"
    )
    await callback.answer()


# --- Контакты и подтверждение ---------------------------------------------


@router.message(BookingForm.name, F.text)
async def on_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not 2 <= len(name) <= 50:
        await message.answer("Введите имя длиной от 2 до 50 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(BookingForm.phone)
    await message.answer(
        "Оставьте номер телефона — нажмите кнопку ниже или введите вручную.", reply_markup=contact_keyboard()
    )


@router.message(BookingForm.phone, F.contact | F.text)
async def on_phone(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number if message.contact else message.text.strip()
    if message.contact and not phone.startswith("+"):
        phone = "+" + phone  # Telegram присылает номер из контакта без «+»
    if not PHONE_RE.match(phone):
        await message.answer("Не похоже на номер телефона. Пример: +7 900 123-45-67")
        return
    await state.update_data(phone=phone)
    await state.set_state(BookingForm.confirm)
    data = await state.get_data()
    service = SERVICES[data["code"]]
    starts = datetime.strptime(data["at"], "%Y%m%d%H%M")
    await message.answer("Спасибо!", reply_markup=main_menu())
    await message.answer(
        "Проверьте запись:\n\n"
        f"<b>{escape(service.title)}</b> — {fmt_dt(starts)}\n"
        f"Стоимость: {service.price} ₽\n"
        f"Имя: {escape(data['name'])}\nТелефон: {escape(phone)}",
        reply_markup=confirm_kb(),
    )


@router.callback_query(ConfirmCB.filter(), StateFilter(BookingForm.confirm))
async def on_confirm(
    callback: CallbackQuery,
    callback_data: ConfirmCB,
    state: FSMContext,
    db: Database,
    settings: Settings,
    bot: Bot,
) -> None:
    data = await state.get_data()
    await state.clear()
    if not callback_data.ok:
        await callback.message.edit_text("Запись отменена. Чтобы начать заново, нажмите «Записаться».")
        await callback.answer()
        return

    service = SERVICES[data["code"]]
    starts = datetime.strptime(data["at"], "%Y%m%d%H%M")
    if starts <= local_now(settings):
        await callback.message.edit_text("Это время уже прошло. Выберите другое через «Записаться».")
        await callback.answer()
        return
    try:
        booking = await db.create(
            user_id=callback.from_user.id,
            client_name=data["name"],
            phone=data["phone"],
            service=service.code,
            starts_at=starts,
            ends_at=starts + timedelta(minutes=service.duration),
        )
    except SlotTakenError:
        await callback.message.edit_text("Увы, это время только что заняли. Выберите другое через «Записаться».")
        await callback.answer()
        return

    await callback.message.edit_text(
        f"✅ Вы записаны!\n\n{booking_text(booking)}\n\nНапомню о визите за {settings.remind_before_hours} ч."
    )
    await callback.answer()
    await notify_admins(bot, settings, f"🆕 Новая запись #{booking.id}\n\n{booking_text(booking)}")


@router.callback_query(ConfirmCB.filter())
async def on_confirm_stale(callback: CallbackQuery) -> None:
    await callback.answer("Эта запись уже обработана", show_alert=True)


# --- Мои записи и отмена --------------------------------------------------


@router.message(F.text == BTN_MY)
async def my_bookings(message: Message, db: Database, settings: Settings) -> None:
    bookings = await db.user_upcoming(message.from_user.id, local_now(settings))
    if not bookings:
        await message.answer("У вас нет предстоящих записей.")
        return
    text = "\n\n".join(booking_text(b) for b in bookings)
    await message.answer(f"<b>Ваши записи</b>\n\n{text}", reply_markup=my_bookings_kb(bookings))


@router.callback_query(CancelCB.filter())
async def on_cancel(
    callback: CallbackQuery, callback_data: CancelCB, db: Database, settings: Settings, bot: Bot
) -> None:
    booking = await db.get(callback_data.booking_id)
    if not booking or not await db.cancel(callback_data.booking_id, user_id=callback.from_user.id):
        await callback.answer("Запись не найдена или уже отменена", show_alert=True)
        return
    await callback.message.edit_text(f"Запись отменена:\n\n{booking_text(booking)}")
    await callback.answer()
    await notify_admins(bot, settings, f"❌ Клиент отменил запись #{booking.id}\n\n{booking_text(booking)}")
