"""Core domain model for wpilot.

One user, one job: fill a shift gap with zero coordinator touches.
Everything here serves the backfill campaign engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _split_tags(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(t.strip().lower() for t in raw.split(";") if t.strip())


@dataclass(frozen=True)
class Shift:
    """A single volunteer shift that must be staffed."""

    shift_id: str
    date: str  # ISO YYYY-MM-DD
    start_time: str  # HH:MM 24h
    end_time: str  # HH:MM 24h
    role: str
    slots_needed: int
    slots_filled: int
    eligibility_tags: frozenset[str] = field(default_factory=frozenset)
    location: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Shift":
        return cls(
            shift_id=row["shift_id"].strip(),
            date=row["date"].strip(),
            start_time=row["start_time"].strip(),
            end_time=row["end_time"].strip(),
            role=row["role"].strip().lower(),
            slots_needed=int(row["slots_needed"]),
            slots_filled=int(row["slots_filled"]),
            eligibility_tags=_split_tags(row.get("eligibility_tags")),
            location=row.get("location", "").strip(),
        )

    @property
    def gap(self) -> int:
        """Unfilled slots. >0 means this shift needs a backfill campaign."""
        return self.slots_needed - self.slots_filled


@dataclass(frozen=True)
class Volunteer:
    """A volunteer who can be asked to cover a shift. Texted, never logged in."""

    volunteer_id: str
    first_name: str
    phone: str
    email: str
    tags: frozenset[str] = field(default_factory=frozenset)
    availability: frozenset[str] = field(default_factory=frozenset)
    reliability_score: float = 0.5
    is_adult: bool = True

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Volunteer":
        return cls(
            volunteer_id=row["volunteer_id"].strip(),
            first_name=row["first_name"].strip(),
            phone=row["phone"].strip(),
            email=row["email"].strip(),
            tags=_split_tags(row.get("tags")),
            availability=_split_tags(row.get("availability")),
            reliability_score=float(row.get("reliability_score", 0.5)),
            is_adult=row.get("is_adult", "true").strip().lower() == "true",
        )
