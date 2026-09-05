"""Campaign engine acceptance tests (scripted channel, zero sleeps)."""

from datetime import datetime
from pathlib import Path

import pytest

from wpilot.campaign import Engine
from wpilot.messaging import SimulatedChannel
from wpilot.store import Store

SEEDS = Path(__file__).resolve().parent.parent / "seeds"
NOON = datetime(2026, 9, 9, 12, 0)  # outside quiet hours
NIGHT = datetime(2026, 9, 9, 22, 30)  # inside quiet hours


def make_store() -> Store:
    s = Store()
    s.import_csvs(SEEDS / "shifts.csv", SEEDS / "volunteers.csv")
    return s


def test_first_candidate_accepts_and_fills():
    store = make_store()  # S1 gap=1; top-ranked Maya answers YES
    engine = Engine(store, SimulatedChannel({"+15550001001": "YES"}), now=NOON,
                    reply_timeout_seconds=0)
    result = engine.run_for_shift("S1")
    assert result.outcome == "FILLED"
    assert result.accepted_by == "V1"
    assert result.needs_review is False
    assert store.get_shift("S1").gap == 0
    kinds = [r["kind"] for r in store.receipts(result.campaign_id)]
    assert kinds == ["offer_sent", "offer_reply", "slot_filled"]


def test_no_skips_to_next_and_books():
    store = make_store()  # Maya NO -> Casey (next) NO -> Devon YES
    engine = Engine(
        store,
        SimulatedChannel({
            "+15550001001": "NO", "+15550001008": "NO", "+15550001002": "YES",
        }),
        now=NOON, reply_timeout_seconds=0,
    )
    result = engine.run_for_shift("S1")
    assert result.outcome == "FILLED" and result.accepted_by == "V2"
    assert result.asked == ["V1", "V8", "V2"]


def test_silence_times_out_and_pool_exhaustion_escalates():
    store = make_store()  # S4 gap=2 but only Jordan is eligible; silent
    engine = Engine(store, SimulatedChannel({}), now=NOON,
                    reply_timeout_seconds=0)
    result = engine.run_for_shift("S4")
    assert result.outcome == "ESCALATED"
    assert result.asked == ["V5"]
    assert "pool exhausted" in result.reason
    assert store.get_shift("S4").gap == 2  # nothing booked


def test_low_reliability_acceptance_flags_review():
    store = make_store()  # only Alex answers; 0.43 < 0.5 threshold
    scripted = {
        "+15550001001": "NO", "+15550001008": "NO", "+15550001002": "NO",
        "+15550001003": "NO", "+15550001005": "NO", "+15550001004": "NO",
        "+15550001006": "YES",
    }
    engine = Engine(store, SimulatedChannel(scripted), now=NOON,
                    reply_timeout_seconds=0)
    result = engine.run_for_shift("S1")
    assert result.outcome == "FILLED" and result.accepted_by == "V6"
    assert result.needs_review is True


def test_quiet_hours_defers_campaign():
    store = make_store()
    channel = SimulatedChannel({"+15550001001": "YES"})
    engine = Engine(store, channel, now=NIGHT, reply_timeout_seconds=0)
    result = engine.run_for_shift("S1")
    assert result.outcome == "ESCALATED"
    assert "quiet hours" in result.reason
    assert store.get_shift("S1").gap == 1
    assert channel.sent == []  # nobody texted at 22:30
    assert len(store.receipts(result.campaign_id)) == 1


def test_ask_cap_skips_over_texted_volunteers():
    store = make_store()
    for _ in range(2):  # Maya already asked twice today by other campaigns
        store.record_ask("C-prior", "V1", "S1")
    engine = Engine(store, SimulatedChannel({"+15550001008": "YES"}), now=NOON,
                    reply_timeout_seconds=0)
    result = engine.run_for_shift("S1")
    assert result.outcome == "FILLED" and result.accepted_by == "V8"
    assert "V1" not in result.asked
