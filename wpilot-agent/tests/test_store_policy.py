"""Day-6 acceptance tests: seeds load, gaps detected, policy enforced."""

from pathlib import Path

import pytest

from wpilot.models import Shift, Volunteer
from wpilot.policy import availability_overlaps, is_eligible, rank_candidates
from wpilot.store import Store, load_shifts_csv, load_volunteers_csv

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


@pytest.fixture()
def store() -> Store:
    s = Store()
    s.import_csvs(SEEDS / "shifts.csv", SEEDS / "volunteers.csv")
    return s


def test_seeds_load():
    assert len(load_shifts_csv(SEEDS / "shifts.csv")) == 4
    assert len(load_volunteers_csv(SEEDS / "volunteers.csv")) == 8


def test_gaps_detected(store: Store):
    gaps = {s.shift_id: s.gap for s in store.gaps()}
    assert gaps == {"S1": 1, "S4": 2}  # S2 and S3 are fully staffed


def test_food_handler_role_restricts_to_trained(store: Store):
    shift = store.get_shift("S2")  # distribution, requires food-handler
    by_id = {v.volunteer_id: v for v in store.volunteers()}
    assert is_eligible(shift, by_id["V3"])[0] is True  # Priya: trained
    assert is_eligible(shift, by_id["V2"])[0] is False  # Devon: no food-handler
    # Riley is a minor AND untrained for this role
    ok, reason = is_eligible(shift, by_id["V7"])
    assert ok is False


def test_adults_only_default(store: Store):
    shift = store.get_shift("S1")  # packing, no required tags
    by_id = {v.volunteer_id: v for v in store.volunteers()}
    ok, reason = is_eligible(shift, by_id["V7"])  # Riley, minor
    assert ok is False and "adults only" in reason
    # Coordinator may relax per shift; then the minor is contactable
    assert is_eligible(shift, by_id["V7"], require_adult=False)[0] is True


def test_driver_role_is_adult_only_even_when_relaxed(store: Store):
    shift = store.get_shift("S4")  # mobile-pantry, requires driver-license
    minor_driver = Volunteer(
        volunteer_id="VX", first_name="Test", phone="+1000", email="",
        tags=frozenset({"driver-license"}), availability=frozenset({"anytime"}),
        is_adult=False,
    )
    ok, _ = is_eligible(shift, minor_driver, require_adult=False)
    assert ok is False


def test_ranking_prefers_overlap_then_reliability(store: Store):
    shift = store.get_shift("S1")  # Thursday morning packing
    ranked = rank_candidates(shift, store.volunteers())
    ids = [v.volunteer_id for v in ranked]
    # Minor excluded by default; all others hold no required tags (empty set)
    assert "V7" not in ids
    assert set(ids) == {"V1", "V2", "V3", "V4", "V5", "V6", "V8"}
    # Weekday-morning volunteers outrank equally-reliable others; top is
    # Casey (0.90, overlaps) or Maya (0.92, overlaps) — both overlap.
    assert ids[0] in ("V1", "V8")
    assert availability_overlaps(shift, ranked[0])


def test_mobile_pantry_only_jordan(store: Store):
    shift = store.get_shift("S4")
    ranked = rank_candidates(shift, store.volunteers())
    assert [v.volunteer_id for v in ranked] == ["V5"]


def test_fill_slot_is_atomic_and_receipted(store: Store):
    before = store.get_shift("S1").slots_filled
    updated = store.fill_slot("S1", "C-test", "V1 accepted via SMS")
    assert updated.slots_filled == before + 1
    receipts = store.receipts("C-test")
    assert len(receipts) == 1 and receipts[0]["kind"] == "slot_filled"
    with pytest.raises(ValueError):
        store.fill_slot("S2", "C-test", "overfill attempt")  # S2 already full


def test_undo_restores_gap_and_cannot_double_undo(store: Store):
    before = store.get_shift("S1").slots_filled
    store.fill_slot("S1", "C-undo", "V1 accepted")
    assert store.get_shift("S1").slots_filled == before + 1
    undone = store.undo_booking("C-undo", "S1")
    assert undone.slots_filled == before
    kinds = [r["kind"] for r in store.receipts("C-undo")]
    assert kinds == ["slot_filled", "booking_undone"]
    with pytest.raises(ValueError):
        store.undo_booking("C-undo", "S1")  # snapshot consumed
    with pytest.raises(ValueError):
        store.undo_booking("C-nope", "S1")  # no snapshot at all
