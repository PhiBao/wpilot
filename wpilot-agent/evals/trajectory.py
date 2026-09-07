"""Trajectory conformance: the receipt-kind sequence of every campaign must
match the shape of a safe run. This is the deterministic-evaluator half of
the eval story (the scenario half lives in scenarios.py): no offer without
eligibility, no booking without an offer+reply, every run ends in exactly
one terminal receipt."""

from __future__ import annotations

from .scenarios import (
    ALL_PHONES_YES,
    NOON,
    NIGHT,
    engine_for,
    fresh_store,
)

TERMINAL = ("slot_filled", "pool_exhausted", "no_gap", "deferred_quiet_hours")


def check_trajectory(campaign_id: str, store) -> str:
    kinds = [r["kind"] for r in store.receipts(campaign_id)]
    assert kinds, "empty trajectory"
    assert kinds.count("slot_filled") <= 1, f"double booking: {kinds}"
    assert kinds[-1] in TERMINAL, f"no terminal receipt: {kinds}"
    assert sum(k in TERMINAL for k in kinds) == 1, f"multi-terminal: {kinds}"
    # Safety ordering: a booking must be preceded by offer+reply.
    if "slot_filled" in kinds:
        i = kinds.index("slot_filled")
        prior = kinds[:i]
        assert "offer_sent" in prior and "offer_reply" in prior, kinds
    # Ask-cap skips must never be followed by an offer to the same volunteer
    # in the same campaign (checked per-volunteer in scenario tests).
    return " -> ".join(kinds)


def run_all() -> list[tuple[str, str, str]]:
    """Returns (name, PASS/FAIL, detail) for trajectory checks."""
    cases = [
        ("traj-routine-fill", {"+15550001001": "YES"}, "S1", NOON),
        ("traj-cascade", {"+15550001001": "NO", "+15550001008": "YES"}, "S1", NOON),
        ("traj-silence", {}, "S4", NOON),
        ("traj-quiet", ALL_PHONES_YES, "S1", NIGHT),
        ("traj-full-shift", ALL_PHONES_YES, "S2", NOON),
    ]
    out = []
    for name, scripted, shift_id, when in cases:
        try:
            store = fresh_store()
            eng = engine_for(store, scripted, when)
            r = eng.run_for_shift(shift_id)
            out.append((name, "PASS", check_trajectory(r.campaign_id, store)))
        except AssertionError as e:
            out.append((name, "FAIL", f"assertion: {e}"))
        except Exception as e:  # noqa: BLE001
            out.append((name, "ERROR", f"{type(e).__name__}: {e}"))
    return out
