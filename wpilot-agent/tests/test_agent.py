"""Agent-layer tests: approval rules, response parsing, construction.

The full model loop is verified live (demo + Bedrock); here we pin the
safety-critical decision surface that the loop depends on.
"""

from pathlib import Path

from strands.hooks import BeforeToolCallEvent

from wpilot.agent import (
    BookingApprovalHook,
    approval_decision,
    build_agent,
    build_tools,
    interpret_approval_response,
)
from wpilot.models import Shift, Volunteer
from wpilot.messaging import SimulatedChannel
from wpilot.store import Store

SEEDS = Path(__file__).resolve().parent.parent / "seeds"


def make_store() -> Store:
    s = Store()
    s.import_csvs(SEEDS / "shifts.csv", SEEDS / "volunteers.csv")
    return s


def test_routine_booking_needs_no_approval():
    store = make_store()
    shift = store.get_shift("S1")
    maya = next(v for v in store.volunteers() if v.volunteer_id == "V1")
    needs, _ = approval_decision(maya, shift)
    assert needs is False


def test_low_reliability_needs_approval():
    store = make_store()
    shift = store.get_shift("S1")
    alex = next(v for v in store.volunteers() if v.volunteer_id == "V6")
    needs, reason = approval_decision(alex, shift)
    assert needs is True and "reliability" in reason


def test_restricted_role_needs_approval_even_for_reliable():
    store = make_store()
    shift = store.get_shift("S4")  # driver-license role
    jordan = next(v for v in store.volunteers() if v.volunteer_id == "V5")
    needs, reason = approval_decision(jordan, shift)
    assert needs is True and "restricted" in reason


def test_response_parsing():
    assert interpret_approval_response("y") == (True, False)
    assert interpret_approval_response("YES") == (True, False)
    assert interpret_approval_response("t") == (True, True)
    assert interpret_approval_response("trust") == (True, True)
    assert interpret_approval_response("n") == (False, False)
    assert interpret_approval_response("no") == (False, False)
    assert interpret_approval_response("") == (False, False)
    assert interpret_approval_response("maybe later") == (False, False)


def test_agent_builds_with_all_tools(tmp_path):
    store = make_store()
    names = {t.tool_name for t in build_tools(store, SimulatedChannel({}))}
    assert names == {
        "list_gaps", "rank_candidates", "send_offer",
        "check_reply", "book_slot", "log_receipt", "read_receipts",
        "undo_booking",
    }
    agent = build_agent(store, SimulatedChannel({}), session_dir=tmp_path)
    assert agent.hooks.has_callbacks()
    assert agent.state is not None


def _callback_owners(agent):
    # Registry is keyed by event class; get_callbacks_for needs an instance,
    # so assert on the keys + owners directly.
    entries = agent.hooks._registered_callbacks.get(BeforeToolCallEvent, [])
    return {type(getattr(e.callback, "__self__", None)).__name__ for e in entries}


def test_hook_registered_on_agent(tmp_path):
    store = make_store()
    agent = build_agent(store, SimulatedChannel({}), session_dir=tmp_path)
    assert "BookingApprovalHook" in _callback_owners(agent)


def test_send_offer_blocks_ineligible(tmp_path):
    from datetime import datetime

    store = make_store()
    send_offer = next(
        t for t in build_tools(
            store, SimulatedChannel({}),
            now_fn=lambda: datetime(2026, 9, 9, 12, 0),
        )
        if t.tool_name == "send_offer"
    )
    # Devon lacks food-handler for S2 -> BLOCKED (call underlying func directly)
    result = send_offer._tool_func(
        volunteer_id="V2", shift_id="S2", campaign_id="C-x"
    )
    assert str(result).startswith("BLOCKED")


def _noon_tools(store, channel):
    from datetime import datetime

    return {
        t.tool_name: t
        for t in build_tools(store, channel,
                             now_fn=lambda: datetime(2026, 9, 9, 12, 0))
    }


def test_book_slot_requires_recorded_yes():
    from wpilot.messaging import SimulatedChannel

    store = make_store()
    tools = _noon_tools(store, SimulatedChannel({"+15550001001": "YES"}))
    refused = tools["book_slot"]._tool_func(
        shift_id="S1", volunteer_id="V1", campaign_id="C-x"
    )
    assert str(refused).startswith("REFUSED")
    tools["send_offer"]._tool_func(
        volunteer_id="V1", shift_id="S1", campaign_id="C-x"
    )
    tools["check_reply"]._tool_func(
        message_id="sim-1", campaign_id="C-x", timeout_seconds=0
    )
    booked = tools["book_slot"]._tool_func(
        shift_id="S1", volunteer_id="V1", campaign_id="C-x"
    )
    assert str(booked).startswith("BOOKED")


def test_book_slot_refuses_decliner_even_if_asked():
    from wpilot.messaging import SimulatedChannel

    store = make_store()
    tools = _noon_tools(store, SimulatedChannel({"+15550001001": "NO"}))
    tools["send_offer"]._tool_func(
        volunteer_id="V1", shift_id="S1", campaign_id="C-x"
    )
    refused = tools["book_slot"]._tool_func(
        shift_id="S1", volunteer_id="V1", campaign_id="C-x"
    )
    assert str(refused).startswith("REFUSED")
    assert store.get_shift("S1").gap == 1  # roster untouched


def test_log_receipt_kind_allowlist():
    from wpilot.messaging import SimulatedChannel

    store = make_store()
    tools = _noon_tools(store, SimulatedChannel({}))
    bad = tools["log_receipt"]._tool_func(
        campaign_id="C-x", kind="slot_filled", detail="forged"
    )
    assert str(bad).startswith("FAILED")
    ok = tools["log_receipt"]._tool_func(
        campaign_id="C-x", kind="escalation", detail="pool exhausted"
    )
    assert str(ok) == "LOGGED"


def test_consent_survives_channel_replacement(tmp_path):
    """The exact proof-run bug: consent must live in the store, so a fresh
    process/channel with the same DB still honors a recorded YES."""
    from wpilot.messaging import SimulatedChannel

    db = tmp_path / "consent.db"
    store = Store(str(db))
    store.import_csvs(
        Path(__file__).resolve().parent.parent / "seeds" / "shifts.csv",
        Path(__file__).resolve().parent.parent / "seeds" / "volunteers.csv",
    )
    tools = _noon_tools(store, SimulatedChannel({"+15550001001": "YES"}))
    tools["send_offer"]._tool_func(
        volunteer_id="V1", shift_id="S1", campaign_id="C-x"
    )
    tools["check_reply"]._tool_func(
        message_id="sim-1", campaign_id="C-x", timeout_seconds=0
    )
    # New channel object, same DB: consent must hold.
    tools2 = _noon_tools(store, SimulatedChannel({}))
    booked = tools2["book_slot"]._tool_func(
        shift_id="S1", volunteer_id="V1", campaign_id="C-x"
    )
    assert str(booked).startswith("BOOKED")
    assert store.get_shift("S1").gap == 0


def test_rank_tool_calls_policy_not_itself():
    """Regression: the rank_candidates TOOL must delegate to the policy
    module, not recurse into itself (live run returned TypeError)."""
    import json

    from wpilot.messaging import SimulatedChannel

    store = make_store()
    tools = _noon_tools(store, SimulatedChannel({}))
    out = tools["rank_candidates"]._tool_func(shift_id="S1")
    ids = [c["volunteer_id"] for c in json.loads(str(out))]
    assert ids[0] == "V1"  # Maya: most reliable weekday-morning packer
    assert "V7" not in ids  # minor excluded by default
