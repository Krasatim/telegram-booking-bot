"""Клавиатуры и callback-данные."""

from __future__ import annotations

from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .config import SERVICES
from .db import Booking

BTN_BOOK = "📅 Записаться"
BTN_MY = "🗂 Мои записи"
BTN_PRICES = "💈 Услуги и цены"

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


def fmt_day(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def fmt_dt(dt: datetime) -> str:
    return f"{fmt_day(dt.date())} в {dt:%H:%M}"


# В callback_data нельзя использовать «:», поэтому дата и время — компактными строками
class ServiceCB(CallbackData, prefix="svc"):
    code: str


class DayCB(CallbackData, prefix="day"):
    code: str
    day: str  # YYYYMMDD


class TimeCB(CallbackData, prefix="time"):
    code: str
    at: str  # YYYYMMDDHHMM


class ConfirmCB(CallbackData, prefix="confirm"):
    ok: bool


class CancelCB(CallbackData, prefix="cancel"):
    booking_id: int


class BackCB(CallbackData, prefix="back"):
    to: str  # services | days
    code: str = ""


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_BOOK)], [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_PRICES)]],
        resize_keyboard=True,
    )


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def services_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in SERVICES.values():
        kb.button(text=f"{s.title} · {s.duration} мин · {s.price} ₽", callback_data=ServiceCB(code=s.code))
    kb.adjust(1)
    return kb.as_markup()


def days_kb(code: str, days: list[date]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=fmt_day(d), callback_data=DayCB(code=code, day=f"{d:%Y%m%d}"))
    kb.adjust(2)
    kb.row(*InlineKeyboardBuilder().button(text="← Услуги", callback_data=BackCB(to="services")).buttons)
    return kb.as_markup()


def times_kb(code: str, slots: list[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in slots:
        kb.button(text=f"{t:%H:%M}", callback_data=TimeCB(code=code, at=f"{t:%Y%m%d%H%M}"))
    kb.adjust(4)
    kb.row(*InlineKeyboardBuilder().button(text="← Даты", callback_data=BackCB(to="days", code=code)).buttons)
    return kb.as_markup()


def confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=ConfirmCB(ok=True))
    kb.button(text="✖️ Отмена", callback_data=ConfirmCB(ok=False))
    return kb.as_markup()


def my_bookings_kb(bookings: list[Booking]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(text=f"Отменить: {fmt_dt(b.starts_at)}", callback_data=CancelCB(booking_id=b.id))
    kb.adjust(1)
    return kb.as_markup()
