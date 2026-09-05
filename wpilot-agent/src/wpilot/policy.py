"""Eligibility policy: who may be asked to cover a shift.

Deterministic and enforced OUTSIDE the LLM (deny-by-default). The agent
proposes outreach order; this module decides who is allowed on the list.
Cedar-backed policies are a later step; the rule surface stays the same.

Rules (v1, safe defaults):
1. Volunteer must hold every eligibility tag the shift requires.
2. Restricted tags (driver-license, food-handler on front roles is fine, but
   any shift tagged `adults-only`, plus driver roles) require is_adult.
3. Ranking: reliability_score desc, then volunteers whose availability token
   overlaps the shift window first.
"""

from __future__ import annotations

from datetime import date

from .models import Shift, Volunteer

# Tags that always require an adult, regardless of shift configuration.
ADULT_ONLY_TAGS = frozenset({"driver-license"})

# Safe default: minors are never contacted unless the coordinator explicitly
# relaxes the policy for a shift. A relaxed-policy minor on a restricted role
# is one of the cases that raises an interrupt instead of booking directly.
REQUIRE_ADULT_DEFAULT = True


def _daypart(shift: Shift) -> str:
    hour = int(shift.start_time.split(":")[0])
    if hour < 12:
        return "mornings"
    if hour < 17:
        return "afternoons"
    return "evenings"


def _weekday_kind(shift: Shift) -> str:
    wd = date.fromisoformat(shift.date).weekday()  # 0 = Monday
    if wd < 5:
        return "weekday"
    return "saturday" if wd == 5 else "sunday"


def availability_overlaps(shift: Shift, volunteer: Volunteer) -> bool:
    """True if any of the volunteer's availability tokens covers the shift."""
    tokens = volunteer.availability
    if not tokens:
        return False
    daypart, kind = _daypart(shift), _weekday_kind(shift)
    candidates = {
        f"{kind}-{daypart}",  # e.g. weekday-mornings
        kind,  # e.g. weekends
        daypart,
        "anytime",
    }
    if kind in ("saturday", "sunday"):
        candidates.add("weekends")
    return bool(tokens & candidates)


def is_eligible(
    shift: Shift, volunteer: Volunteer, require_adult: bool = REQUIRE_ADULT_DEFAULT
) -> tuple[bool, str]:
    """Return (allowed, reason). Deny-by-default."""
    if require_adult and not volunteer.is_adult:
        return False, "policy: adults only (coordinator may relax per shift)"
    if not shift.eligibility_tags <= volunteer.tags:
        missing = sorted(shift.eligibility_tags - volunteer.tags)
        return False, f"missing tags: {', '.join(missing)}"
    if (shift.eligibility_tags & ADULT_ONLY_TAGS) and not volunteer.is_adult:
        return False, "restricted role requires an adult"
    return True, "eligible"


def rank_candidates(shift: Shift, volunteers: list[Volunteer]) -> list[Volunteer]:
    """Eligible volunteers, best first: availability overlap, then reliability."""
    eligible = [v for v in volunteers if is_eligible(shift, v)[0]]
    return sorted(
        eligible,
        key=lambda v: (availability_overlaps(shift, v), v.reliability_score),
        reverse=True,
    )
