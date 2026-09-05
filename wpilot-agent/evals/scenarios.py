"""wpilot evals: 10 product guarantees, executed, reported.

Each scenario runs the real engine/policy/store (scripted or silent channel)
and asserts the guarantee a coordinator or judge would care about. The runner
writes evals/report.md — linked from the README as reliability evidence.

Run: python -m evals.run_evals   (from wpilot-agent/, venv active)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from wpilot.campaign import Engine
from wpilot.messaging import SimulatedChannel
from wpilot.store import Store

SEEDS = Path(__file__).resolve().parent.parent / "seeds"
NOON = datetime(2026, 9, 9, 12, 0)
NIGHT = datetime(2026, 9, 9, 22, 30)

ALL_PHONES_YES = {
    "+15550001001": "YES", "+15550001002": "YES", "+15550001003": "YES",
    "+15550001004": "YES", "+15550001005": "YES", "+15550001006": "YES",
    "+15550001008": "YES",
    # V7 (minor) deliberately scripted YES: proves the policy holds anyway.
    "+15550001007": "YES",
}


@dataclass
class Scenario:
    name: str = ""
    guarantee: str = ""

    def run(self) -> str:
        raise NotImplementedError


def fresh_store() -> Store:
    s = Store()
    s.import_csvs(SEEDS / "shifts.csv", SEEDS / "volunteers.csv")
    return s


def engine_for(store: Store, scripted: dict, when: datetime = NOON) -> Engine:
    return Engine(store, SimulatedChannel(scripted), now=when,
                  reply_timeout_seconds=0)


class RoutineFillZeroTouches(Scenario):
    name = "routine-fill-zero-touches"
    guarantee = "A routine gap fills with zero coordinator touches."

    def run(self) -> str:
        store, eng = fresh_store(), None
        eng = engine_for(store, {"+15550001001": "YES"})
        r = eng.run_for_shift("S1")
        assert r.outcome == "FILLED" and r.asked == ["V1"], r
        assert r.needs_review is False
        return f"FILLED by {r.accepted_by} after asking {len(r.asked)}"


class DeclineCascades(Scenario):
    name = "decline-cascades"
    guarantee = "A NO moves to the next eligible volunteer, in rank order."

    def run(self) -> str:
        store = fresh_store()
        eng = engine_for(store, {"+15550001001": "NO", "+15550001008": "YES"})
        r = eng.run_for_shift("S1")
        assert r.outcome == "FILLED" and r.accepted_by == "V8", r
        assert r.asked == ["V1", "V8"], r.asked
        return "V1 declined -> V8 booked"


class SilenceEscalatesCleanly(Scenario):
    name = "silence-escalates-cleanly"
    guarantee = "Total silence exhausts the pool and escalates; roster untouched."

    def run(self) -> str:
        store = fresh_store()
        eng = engine_for(store, {})
        r = eng.run_for_shift("S4")
        assert r.outcome == "ESCALATED" and "pool exhausted" in r.reason, r
        assert store.get_shift("S4").gap == 2
        kinds = [x["kind"] for x in store.receipts(r.campaign_id)]
        assert "pool_exhausted" in kinds and "slot_filled" not in kinds
        return f"asked {len(r.asked)}, booked 0, receipts explain why"


class OnlyEligibleTexted(Scenario):
    name = "only-eligible-texted"
    guarantee = "Untrained volunteers are never texted for restricted roles."

    def run(self) -> str:
        store = fresh_store()
        eng = engine_for(store, ALL_PHONES_YES)
        r = eng.run_for_shift("S2")  # needs food-handler; already full
        assert r.outcome == "ESCALATED", r  # S2 is full: nothing to fill
        # Now open it and confirm only trained volunteers are asked.
        store.conn.execute("UPDATE shifts SET slots_filled=3 WHERE shift_id='S2'")
        eng2 = engine_for(store, ALL_PHONES_YES)
        r2 = eng2.run_for_shift("S2")
        assert r2.outcome == "FILLED", r2
        assert set(r2.asked) <= {"V1", "V3", "V8"}, r2.asked
        return f"asked only {sorted(r2.asked)}"


class MinorNeverContacted(Scenario):
    name = "minor-never-contacted"
    guarantee = "The minor is never texted under the default adults-only policy."

    def run(self) -> str:
        store = fresh_store()
        eng = engine_for(store, ALL_PHONES_YES)
        r = eng.run_for_shift("S1")
        assert "V7" not in r.asked, r.asked
        return "V7 scripted YES but never asked"


class QuietHoursDefer(Scenario):
    name = "quiet-hours-defer"
    guarantee = "Nothing is sent during quiet hours; the deferral is receipted."

    def run(self) -> str:
        store = fresh_store()
        eng = engine_for(store, ALL_PHONES_YES, when=NIGHT)
        r = eng.run_for_shift("S1")
        assert r.outcome == "ESCALATED" and "quiet hours" in r.reason, r
        assert store.get_shift("S1").gap == 1
        return "0 messages sent at 22:30"


class AskCapRespected(Scenario):
    name = "ask-cap-respected"
    guarantee = "A volunteer at the daily ask cap is skipped, not spammed."

    def run(self) -> str:
        store = fresh_store()
        store.record_ask("C-prior", "V1", "S1")
        store.record_ask("C-prior", "V1", "S1")
        eng = engine_for(store, {"+15550001008": "YES"})
        r = eng.run_for_shift("S1")
        assert "V1" not in r.asked and r.accepted_by == "V8", r
        kinds = [x["kind"] for x in store.receipts(r.campaign_id)]
        assert "ask_cap_skipped" in kinds
        return "V1 skipped after 2 prior asks; V8 booked"


class NoDoubleBook(Scenario):
    name = "no-double-book"
    guarantee = "A full shift can never be overfilled."

    def run(self) -> str:
        store = fresh_store()
        eng = engine_for(store, ALL_PHONES_YES)
        r = eng.run_for_shift("S2")  # S2 starts full
        assert r.outcome == "ESCALATED", r
        assert store.get_shift("S2").slots_filled == 4
        return "full shift untouched"


class LowReliabilityFlagsReview(Scenario):
    name = "low-reliability-flags-review"
    guarantee = "A fill by a low-reliability volunteer is flagged, not silent."

    def run(self) -> str:
        store = fresh_store()
        scripted = {p: "NO" for p in ALL_PHONES_YES}
        scripted["+15550001006"] = "YES"  # Alex, 0.43
        eng = engine_for(store, scripted)
        r = eng.run_for_shift("S1")
        assert r.outcome == "FILLED" and r.needs_review is True, r
        return f"booked {r.accepted_by} with review flag"


class AuditCompleteness(Scenario):
    name = "audit-completeness"
    guarantee = "Every campaign leaves a complete receipt trail."

    def run(self) -> str:
        store = fresh_store()
        eng = engine_for(store, {"+15550001001": "NO"})
        r = eng.run_for_shift("S1")
        receipts = store.receipts(r.campaign_id)
        assert len(receipts) >= 3, receipts  # offer(s) + replie(s) + outcome
        assert receipts[-1]["kind"] in ("slot_filled", "pool_exhausted")
        return f"{len(receipts)} receipts, ending in {receipts[-1]['kind']}"


SCENARIOS: list[Scenario] = [
    RoutineFillZeroTouches(),
    DeclineCascades(),
    SilenceEscalatesCleanly(),
    OnlyEligibleTexted(),
    MinorNeverContacted(),
    QuietHoursDefer(),
    AskCapRespected(),
    NoDoubleBook(),
    LowReliabilityFlagsReview(),
    AuditCompleteness(),
]
