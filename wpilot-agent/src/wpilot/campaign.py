"""Backfill campaign engine v1.

One gap -> ranked offers -> commitment or escalation. Deterministic; the
Strands agent (Day 8) will own the loop and call these same primitives as
tools, with interrupts for the escalation path.

Terminal outcomes per gap: FILLED or ESCALATED. A fill by a low-reliability
volunteer is flagged needs_review so the interrupt layer can route it to the
coordinator instead of booking silently.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime

from . import messaging
from .messaging import SimulatedChannel, parse_reply
from .models import Shift, Volunteer
from .policy import rank_candidates
from .store import Store

REVIEW_RELIABILITY_BELOW = 0.5  # acceptances under this flag coordinator review


@dataclass
class CampaignResult:
    campaign_id: str
    shift_id: str
    outcome: str  # FILLED | ESCALATED
    accepted_by: str = ""  # volunteer_id
    needs_review: bool = False
    reason: str = ""
    asked: list[str] = field(default_factory=list)  # volunteer_ids contacted


def offer_text(first_name: str, shift: Shift, org_name: str = "Harbor Pantry") -> str:
    return (
        f"Hi {first_name}! {org_name} needs 1 more volunteer for "
        f"{shift.role} on {shift.date} {shift.start_time}-{shift.end_time} "
        f"({shift.location}). Reply YES to cover it, or NO. "
        f"- wpilot for {org_name}"
    )


class Engine:
    def __init__(
        self,
        store: Store,
        channel: SimulatedChannel,
        org_name: str = "Harbor Pantry",
        reply_timeout_seconds: float = 600.0,
        max_asks_per_volunteer_per_day: int = messaging.MAX_ASKS_PER_VOLUNTEER_PER_DAY,
        now: datetime | None = None,
    ) -> None:
        self.store = store
        self.channel = channel
        self.org_name = org_name
        self.reply_timeout_seconds = reply_timeout_seconds
        self.max_asks = max_asks_per_volunteer_per_day
        self.now = now or datetime.now()
        self._campaigns = itertools.count(1)

    def run_for_shift(self, shift_id: str) -> CampaignResult:
        campaign_id = f"C-{next(self._campaigns)}"
        shift = self.store.get_shift(shift_id)
        result = CampaignResult(
            campaign_id=campaign_id, shift_id=shift_id, outcome="ESCALATED"
        )

        if shift.gap <= 0:
            result.reason = "shift already full"
            self.store.add_receipt(campaign_id, "no_gap", f"{shift_id} full on entry")
            return result
        if messaging.in_quiet_hours(self.now):
            result.reason = "quiet hours — campaign deferred"
            self.store.add_receipt(campaign_id, "deferred_quiet_hours", shift_id)
            return result

        candidates = rank_candidates(shift, self.store.volunteers())
        if not candidates:
            result.reason = "no eligible volunteers"
            self.store.add_receipt(campaign_id, "pool_exhausted", shift_id)
            return result

        for volunteer in candidates:
            if self.store.get_shift(shift_id).gap <= 0:
                break  # another acceptance filled it (multi-slot safety)
            if self.store.asks_today(volunteer.volunteer_id) >= self.max_asks:
                self.store.add_receipt(
                    campaign_id, "ask_cap_skipped",
                    f"{volunteer.volunteer_id} already asked {self.max_asks}x today",
                )
                continue
            answer = self._offer(campaign_id, shift, volunteer)
            result.asked.append(volunteer.volunteer_id)
            if answer == "YES":
                updated = self.store.fill_slot(
                    shift_id, campaign_id,
                    f"{volunteer.volunteer_id} ({volunteer.first_name}) accepted",
                )
                result.outcome = "FILLED"
                result.accepted_by = volunteer.volunteer_id
                result.reason = (
                    f"filled by {volunteer.first_name}; "
                    f"{updated.gap} slot(s) still open" if updated.gap else
                    f"filled by {volunteer.first_name}; shift now full"
                )
                if volunteer.reliability_score < REVIEW_RELIABILITY_BELOW:
                    result.needs_review = True
                    result.reason += " (flagged: low reliability — coordinator review)"
                return result

        result.reason = f"pool exhausted after asking {len(result.asked)} volunteer(s)"
        self.store.add_receipt(campaign_id, "pool_exhausted", result.reason)
        return result

    def _offer(
        self, campaign_id: str, shift: Shift, volunteer: Volunteer
    ) -> str:
        body = offer_text(volunteer.first_name, shift, self.org_name)
        msg = self.channel.send(volunteer.phone, body)
        self.store.record_ask(campaign_id, volunteer.volunteer_id, shift.shift_id)
        self.store.add_receipt(
            campaign_id, "offer_sent",
            f"asked {volunteer.first_name} ({volunteer.volunteer_id}): {msg.message_id}",
        )
        reply = self.channel.await_reply(msg, self.reply_timeout_seconds)
        if reply is None:
            self.store.add_receipt(
                campaign_id, "offer_timeout",
                f"{volunteer.first_name} did not reply",
            )
            return "TIMEOUT"
        answer = parse_reply(reply.body)
        self.store.add_receipt(
            campaign_id, "offer_reply",
            f"{volunteer.first_name} replied: {answer}",
        )
        return answer
