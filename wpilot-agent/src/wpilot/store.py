"""Roster store: CSV import + SQLite persistence.

CSV is the Day-6 floor for org onboarding (upload a shift sheet, done).
Google Sheets import is a later step; it will reuse these same row shapes.
"""

from __future__ import annotations

import csv
import sqlite3
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


class Store:
    """Tiny SQLite roster store. One file per org."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

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

    def shifts(self) -> list[Shift]:
        rows = self.conn.execute("SELECT * FROM shifts ORDER BY date, start_time").fetchall()
        return [self._row_to_shift(r) for r in rows]

    def volunteers(self) -> list[Volunteer]:
        rows = self.conn.execute(
            "SELECT * FROM volunteers ORDER BY reliability_score DESC"
        ).fetchall()
        return [self._row_to_volunteer(r) for r in rows]

    def gaps(self) -> list[Shift]:
        """Shifts with unfilled slots — the backfill workload."""
        return [s for s in self.shifts() if s.gap > 0]

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
                "UPDATE shifts SET slots_filled = slots_filled + 1 WHERE shift_id = ?",
                (shift_id,),
            )
            self.conn.execute(
                "INSERT INTO receipts (campaign_id, kind, detail) VALUES (?,?,?)",
                (campaign_id, "slot_filled", detail),
            )
        return self.get_shift(shift_id)

    def add_receipt(self, campaign_id: str, kind: str, detail: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO receipts (campaign_id, kind, detail) VALUES (?,?,?)",
                (campaign_id, kind, detail),
            )

    def record_ask(self, campaign_id: str, volunteer_id: str, shift_id: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO asks (campaign_id, volunteer_id, shift_id) VALUES (?,?,?)",
                (campaign_id, volunteer_id, shift_id),
            )

    def asks_today(self, volunteer_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM asks "
            "WHERE volunteer_id = ? AND date(asked_at) = date('now')",
            (volunteer_id,),
        ).fetchone()
        return int(row["n"])

    def receipts(self, campaign_id: str = "") -> list[dict]:
        if campaign_id:
            rows = self.conn.execute(
                "SELECT * FROM receipts WHERE campaign_id = ? ORDER BY id",
                (campaign_id,),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM receipts ORDER BY id").fetchall()
        return [dict(r) for r in rows]

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
