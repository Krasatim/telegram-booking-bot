"""Хранилище записей на SQLite.

Время хранится как локальное время заведения (без часового пояса) в формате ISO.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    client_name TEXT    NOT NULL,
    phone       TEXT    NOT NULL,
    service     TEXT    NOT NULL,
    starts_at   TEXT    NOT NULL,
    ends_at     TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',
    reminded    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bookings_starts ON bookings (starts_at);
"""


@dataclass
class Booking:
    id: int
    user_id: int
    client_name: str
    phone: str
    service: str
    starts_at: datetime
    ends_at: datetime
    status: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> Booking:
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            client_name=row["client_name"],
            phone=row["phone"],
            service=row["service"],
            starts_at=datetime.fromisoformat(row["starts_at"]),
            ends_at=datetime.fromisoformat(row["ends_at"]),
            status=row["status"],
        )


class SlotTakenError(Exception):
    """Слот заняли, пока клиент оформлял запись."""


class Database:
    def __init__(self, path: str):
        self.path = path

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def init(self) -> None:
        async with self._connect() as conn:
            await conn.executescript(SCHEMA)
            await conn.commit()

    async def busy_intervals(self, day: date) -> list[tuple[datetime, datetime]]:
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT starts_at, ends_at FROM bookings "
                "WHERE status = 'active' AND starts_at < ? AND ends_at > ?",
                (end.isoformat(), start.isoformat()),
            )
            rows = await cursor.fetchall()
        return [(datetime.fromisoformat(r["starts_at"]), datetime.fromisoformat(r["ends_at"])) for r in rows]

    async def create(
        self, user_id: int, client_name: str, phone: str, service: str, starts_at: datetime, ends_at: datetime
    ) -> Booking:
        async with self._connect() as conn:
            # BEGIN IMMEDIATE блокирует запись: две параллельные брони не займут один слот
            await conn.execute("BEGIN IMMEDIATE")
            cursor = await conn.execute(
                "SELECT 1 FROM bookings WHERE status = 'active' AND starts_at < ? AND ends_at > ?",
                (ends_at.isoformat(), starts_at.isoformat()),
            )
            if await cursor.fetchone():
                await conn.rollback()
                raise SlotTakenError
            cursor = await conn.execute(
                "INSERT INTO bookings (user_id, client_name, phone, service, starts_at, ends_at, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    client_name,
                    phone,
                    service,
                    starts_at.isoformat(),
                    ends_at.isoformat(),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            booking_id = cursor.lastrowid
            await conn.commit()
        return Booking(booking_id, user_id, client_name, phone, service, starts_at, ends_at, "active")

    async def get(self, booking_id: int) -> Booking | None:
        async with self._connect() as conn:
            cursor = await conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
            row = await cursor.fetchone()
        return Booking.from_row(row) if row else None

    async def user_upcoming(self, user_id: int, now: datetime) -> list[Booking]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM bookings WHERE user_id = ? AND status = 'active' AND starts_at > ? "
                "ORDER BY starts_at",
                (user_id, now.isoformat()),
            )
            rows = await cursor.fetchall()
        return [Booking.from_row(r) for r in rows]

    async def day_bookings(self, day: date) -> list[Booking]:
        start = datetime.combine(day, datetime.min.time())
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM bookings WHERE status = 'active' AND starts_at >= ? AND starts_at < ? "
                "ORDER BY starts_at",
                (start.isoformat(), (start + timedelta(days=1)).isoformat()),
            )
            rows = await cursor.fetchall()
        return [Booking.from_row(r) for r in rows]

    async def cancel(self, booking_id: int, user_id: int | None = None) -> bool:
        """Отменяет запись. Если передан user_id — только запись этого клиента."""
        query = "UPDATE bookings SET status = 'cancelled' WHERE id = ? AND status = 'active'"
        params: tuple = (booking_id,)
        if user_id is not None:
            query += " AND user_id = ?"
            params += (user_id,)
        async with self._connect() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()
            return cursor.rowcount > 0

    async def due_reminders(self, now: datetime, before: timedelta) -> list[Booking]:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "SELECT * FROM bookings WHERE status = 'active' AND reminded = 0 "
                "AND starts_at > ? AND starts_at <= ?",
                (now.isoformat(), (now + before).isoformat()),
            )
            rows = await cursor.fetchall()
        return [Booking.from_row(r) for r in rows]

    async def mark_reminded(self, booking_id: int) -> None:
        async with self._connect() as conn:
            await conn.execute("UPDATE bookings SET reminded = 1 WHERE id = ?", (booking_id,))
            await conn.commit()
