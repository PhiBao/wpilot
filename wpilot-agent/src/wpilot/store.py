"""Roster store: CSV import + SQLite persistence.

CSV is the Day-6 floor for org onboarding (upload a shift sheet, done).
Google Sheets import is a later step; it will reuse these same row shapes.
"""

from __future__ import annotations

import csv
import sqlite3
import threading
from functools import wraps
from pathlib import Path

from .models import Shift, Volunteer

SCHEMA = """
CREATE TABLE IF NOT EXISTS shifts (
    shift_id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    role TEXT NOT NULL,
    slots_needed INTEGER NOT NULL,
    slots_filled INTEGER NOT NULL,
    eligibility_tags TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS volunteers (
    volunteer_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    availability TEXT NOT NULL DEFAULT '',
    reliability_score REAL NOT NULL DEFAULT 0.5,
    is_adult INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    campaign_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS asks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asked_at TEXT NOT NULL DEFAULT (datetime('now')),
    campaign_id TEXT NOT NULL DEFAULT '',
    volunteer_id TEXT NOT NULL,
    shift_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    campaign_id TEXT NOT NULL,
    shift_id TEXT NOT NULL,
    slots_filled_before INTEGER NOT NULL,
    undone INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS offers (
    message_id TEXT PRIMARY KEY,
    sent_at TEXT NOT NULL DEFAULT (datetime('now')),
    campaign_id TEXT NOT NULL,
    shift_id TEXT NOT NULL,
    volunteer_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS replies (
    message_id TEXT PRIMARY KEY,
    replied_at TEXT NOT NULL DEFAULT (datetime('now')),
    answer TEXT NOT NULL
);
"""


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_shifts_csv(path: str | Path) -> list[Shift]:
    return [Shift.from_row(r) for r in _read_csv(path)]


def load_volunteers_csv(path: str | Path) -> list[Volunteer]:
    return [Volunteer.from_row(r) for r in _read_csv(path)]


def _join(tags: frozenset[str]) -> str:
    return ";".join(sorted(tags))


def _locked(fn):
    """Serialize SQLite access (server threadpool shares one connection)."""

    @wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)

    return wrapper


class Store:
    """Tiny SQLite roster store. One file per org."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        # check_same_thread=False: the demo server runs endpoints in a
        # threadpool. All access is serialized by self._lock (RLock: gaps()
        # calls shifts(), fill_slot() calls get_shift()).
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self.conn.executescript(SCHEMA)

    @_locked
    def import_csvs(self, shifts_csv: str | Path, volunteers_csv: str | Path) -> None:
        shifts = load_shifts_csv(shifts_csv)
        volunteers = load_volunteers_csv(volunteers_csv)
        with self.conn:
            for s in shifts:
                self.conn.execute(
                    "INSERT OR REPLACE INTO shifts VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        s.shift_id, s.date, s.start_time, s.end_time, s.role,
                        s.slots_needed, s.slots_filled, _join(s.eligibility_tags),
                        s.location,
                    ),
                )
            for v in volunteers:
                self.conn.execute(
                    "INSERT OR REPLACE INTO volunteers VALUES (?,?,?,?,?,?,?,?)",
                    (
                        v.volunteer_id, v.first_name, v.phone, v.email,
                        _join(v.tags), _join(v.availability),
                        v.reliability_score, int(v.is_adult),
                    ),
                )

    @_locked
    def shifts(self) -> list[Shift]:
        rows = self.conn.execute("SELECT * FROM shifts ORDER BY date, start_time").fetchall()
        return [self._row_to_shift(r) for r in rows]

    @_locked
    def volunteers(self) -> list[Volunteer]:
        rows = self.conn.execute(
            "SELECT * FROM volunteers ORDER BY reliability_score DESC"
        ).fetchall()
        return [self._row_to_volunteer(r) for r in rows]

    def gaps(self) -> list[Shift]:
        """Shifts with unfilled slots — the backfill workload."""
        return [s for s in self.shifts() if s.gap > 0]

    @_locked
    def fill_slot(self, shift_id: str, campaign_id: str, detail: str) -> Shift:
        """Atomically increment slots_filled and record a receipt. Returns updated shift."""
        with self.conn:
            row = self.conn.execute(
                "SELECT * FROM shifts WHERE shift_id = ?", (shift_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown shift {shift_id}")
            shift = self._row_to_shift(row)
            if shift.gap <= 0:
                raise ValueError(f"shift {shift_id} already full")
            self.conn.execute(
                "INSERT INTO snapshots (campaign_id, shift_id, slots_filled_before)"
                " VALUES (?,?,?)",
                (campaign_id, shift_id, shift.slots_filled),
            )
            self.conn.execute(
                "UPDATE shifts SET slots_filled = slots_filled + 1 WHERE shift_id = ?",
                (shift_id,),
            )
            self.conn.execute(
                "INSERT INTO receipts (campaign_id, kind, detail) VALUES (?,?,?)",
                (campaign_id, "slot_filled", detail),
            )
        return self.get_shift(shift_id)

    @_locked
    def undo_booking(self, campaign_id: str, shift_id: str) -> Shift:
        """Undo one booking from a campaign. Consumes the campaign's latest
        snapshot so repeats fail loudly instead of double-undoing; removes
        exactly one fill and receipts the revert."""
        with self.conn:
            row = self.conn.execute(
                "SELECT * FROM snapshots WHERE campaign_id = ? AND shift_id = ?"
                " AND undone = 0 ORDER BY id DESC LIMIT 1",
                (campaign_id, shift_id),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"nothing to undo for {campaign_id}/{shift_id}"
                )
            current = self._row_to_shift(
                self.conn.execute(
                    "SELECT * FROM shifts WHERE shift_id = ?", (shift_id,)
                ).fetchone()
            )
            if current.slots_filled <= 0:
                raise ValueError(f"shift {shift_id} is already empty")
            restored = current.slots_filled - 1
            self.conn.execute(
                "UPDATE shifts SET slots_filled = ? WHERE shift_id = ?",
                (restored, shift_id),
            )
            self.conn.execute(
                "UPDATE snapshots SET undone = 1 WHERE id = ?", (row["id"],)
            )
            self.conn.execute(
                "INSERT INTO receipts (campaign_id, kind, detail) VALUES (?,?,?)",
                (campaign_id, "booking_undone",
                 f"reverted {shift_id} to {restored} filled (was {current.slots_filled})"),
            )
        return self.get_shift(shift_id)

    @_locked
    def add_receipt(self, campaign_id: str, kind: str, detail: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO receipts (campaign_id, kind, detail) VALUES (?,?,?)",
                (campaign_id, kind, detail),
            )

    @_locked
    def record_ask(self, campaign_id: str, volunteer_id: str, shift_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO asks (campaign_id, volunteer_id, shift_id) VALUES (?,?,?)",
                (campaign_id, volunteer_id, shift_id),
            )

    @_locked
    def asks_today(self, volunteer_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM asks "
            "WHERE volunteer_id = ? AND date(asked_at) = date('now')",
            (volunteer_id,),
        ).fetchone()
        return int(row["n"])

    @_locked
    def record_offer(self, message_id: str, campaign_id: str,
                     shift_id: str, volunteer_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO offers "
                "(message_id, campaign_id, shift_id, volunteer_id) "
                "VALUES (?,?,?,?)",
                (message_id, campaign_id, shift_id, volunteer_id),
            )

    @_locked
    def record_reply(self, message_id: str, answer: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO replies (message_id, answer) "
                "VALUES (?,?)",
                (message_id, answer),
            )

    @_locked
    def consent_yes(self, campaign_id: str, shift_id: str,
                    volunteer_id: str) -> bool:
        """Durable consent: a recorded YES reply to an offer for this exact
        (campaign, shift, volunteer). Survives process restarts — the booking
        tool trusts this, never the model's word."""
        row = self.conn.execute(
            "SELECT 1 FROM offers JOIN replies USING (message_id) "
            "WHERE campaign_id = ? AND shift_id = ? AND volunteer_id = ? "
            "AND answer = 'YES' LIMIT 1",
            (campaign_id, shift_id, volunteer_id),
        ).fetchone()
        return row is not None

    @_locked
    def receipts(self, campaign_id: str = "") -> list[dict]:
        if campaign_id:
            rows = self.conn.execute(
                "SELECT * FROM receipts WHERE campaign_id = ? ORDER BY id",
                (campaign_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM receipts ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    @_locked
    def get_shift(self, shift_id: str) -> Shift:
        row = self.conn.execute(
            "SELECT * FROM shifts WHERE shift_id = ?", (shift_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown shift {shift_id}")
        return self._row_to_shift(row)

    @staticmethod
    def _row_to_shift(r: sqlite3.Row) -> Shift:
        return Shift(
            shift_id=r["shift_id"], date=r["date"], start_time=r["start_time"],
            end_time=r["end_time"], role=r["role"], slots_needed=r["slots_needed"],
            slots_filled=r["slots_filled"],
            eligibility_tags=frozenset(t for t in r["eligibility_tags"].split(";") if t),
            location=r["location"],
        )

    @staticmethod
    def _row_to_volunteer(r: sqlite3.Row) -> Volunteer:
        return Volunteer(
            volunteer_id=r["volunteer_id"], first_name=r["first_name"],
            phone=r["phone"], email=r["email"],
            tags=frozenset(t for t in r["tags"].split(";") if t),
            availability=frozenset(t for t in r["availability"].split(";") if t),
            reliability_score=r["reliability_score"], is_adult=bool(r["is_adult"]),
        )
