"""wpilot campaign agent: a Strands loop over deterministic campaign tools.

Division of labor (the product thesis in code):
- The agent proposes: which gap to work, whom to ask, in what order.
- Deterministic code disposes: eligibility, safety rails, atomic booking.
- The approval hook interrupts the loop when a commitment needs a human:
  low-reliability volunteer, restricted role, or anything ambiguous.

Interrupt answers: "y" approves once, "t" approves and remembers trust in
agent state (persisted by the session manager, so trust survives restarts),
anything else denies and the tool call is cancelled with an explanation the
agent can act on (ask the next candidate, or escalate).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry
from strands.session import FileSessionManager

from .campaign import REVIEW_RELIABILITY_BELOW, offer_text
from .messaging import SimulatedChannel, parse_reply
from .models import Shift, Volunteer
from .policy import ADULT_ONLY_TAGS, is_eligible, rank_candidates
from .store import Store

SYSTEM_PROMPT = """You are wpilot, the backfill coordinator for a volunteer-run \
food pantry. Your job: fill understaffed shifts by texting volunteers.

Loop, one gap at a time:
1. Call list_gaps. Pick the most urgent gap (earliest date first).
2. Call rank_candidates for that shift. Text candidates in order with \
send_offer (one at a time — wait for each reply with check_reply before \
moving on).
3. On YES: call book_slot to lock them in, then summarize the receipt.
4. On NO/silence: thank them implicitly by moving on — ask the next candidate.
5. If the candidate list is exhausted, or book_slot is denied, report the \
escalation clearly: which shift, whom you asked, what happened, and what the \
coordinator should decide. Never invent volunteer replies. Never text anyone \
outside the ranked list.

You are careful, brief, and auditable. Every commitment goes through book_slot \
— no exceptions."""

TRUST_STATE_KEY = "wpilot-trust"


def approval_decision(volunteer: Volunteer, shift: Shift) -> tuple[bool, str]:
    """Pure rule: does booking this volunteer need a human? Deny-by-default
    stays in policy.py; this decides whether the booking also needs approval."""
    if volunteer.reliability_score < REVIEW_RELIABILITY_BELOW:
        return True, (
            f"low reliability ({volunteer.reliability_score:.2f} < "
            f"{REVIEW_RELIABILITY_BELOW:.2f}) — coordinator should confirm"
        )
    if shift.eligibility_tags & ADULT_ONLY_TAGS:
        return True, "restricted role — coordinator should confirm assignee"
    return False, "routine booking"


def interpret_approval_response(response: Any) -> tuple[bool, bool]:
    """Normalize an interrupt answer -> (approved, remember_trust)."""
    text = str(response).strip().lower()
    if text in ("t", "trust", "yes-always", "always"):
        return True, True
    if text in ("y", "yes", "yep", "ok", "approve", "approved"):
        return True, False
    return False, False


class BookingApprovalHook(HookProvider):
    """Gate book_slot behind a human interrupt when approval_decision says so."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.approve)

    def approve(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use["name"] != "book_slot":
            return
        tool_input = event.tool_use["input"]
        try:
            shift = self.store.get_shift(tool_input["shift_id"])
            volunteer = next(
                v for v in self.store.volunteers()
                if v.volunteer_id == tool_input["volunteer_id"]
            )
        except (KeyError, StopIteration):
            event.cancel_tool = "Unknown shift or volunteer — re-check IDs and try again."
            return

        if event.agent.state.get(TRUST_STATE_KEY) == "t":
            return  # coordinator already trusts routine bookings

        needs_approval, reason = approval_decision(volunteer, shift)
        if not needs_approval:
            return

        answer = event.interrupt(
            "wpilot-booking-approval",
            reason={
                "shift_id": shift.shift_id,
                "role": shift.role,
                "date": shift.date,
                "window": f"{shift.start_time}-{shift.end_time}",
                "volunteer": volunteer.first_name,
                "volunteer_id": volunteer.volunteer_id,
                "reliability": volunteer.reliability_score,
                "why": reason,
            },
        )
        approved, remember = interpret_approval_response(answer)
        if remember:
            event.agent.state.set(TRUST_STATE_KEY, "t")
        if not approved:
            event.cancel_tool = (
                f"Coordinator declined booking {volunteer.first_name} on "
                f"{shift.shift_id} ({reason}). Ask the next candidate, or "
                "escalate if the list is exhausted."
            )


def build_tools(
    store: Store,
    channel: SimulatedChannel,
    now_fn: Callable[[], datetime] | None = None,
) -> list:
    """Agent tools. All safety-critical checks live here or in policy.py —
    never in the prompt. now_fn is injectable for deterministic tests."""
    _now = now_fn or datetime.now

    @tool
    def list_gaps() -> str:
        """List shifts with unfilled slots. Returns JSON."""
        gaps = store.gaps()
        return json.dumps([
            {"shift_id": s.shift_id, "date": s.date,
             "window": f"{s.start_time}-{s.end_time}", "role": s.role,
             "gap": s.gap, "location": s.location}
            for s in gaps
        ])

    @tool
    def rank_candidates(shift_id: str) -> str:
        """Ranked eligible volunteers for a shift. Returns JSON. Text them in order."""
        shift = store.get_shift(shift_id)
        ranked = rank_candidates(shift, store.volunteers())
        return json.dumps([
            {"volunteer_id": v.volunteer_id, "first_name": v.first_name,
             "reliability": v.reliability_score}
            for v in ranked
        ])

    @tool
    def send_offer(volunteer_id: str, shift_id: str, campaign_id: str) -> str:
        """Text a volunteer a cover offer. Enforces ask caps and quiet hours.
        Returns the message ID for check_reply."""
        from . import messaging as _messaging

        if _messaging.in_quiet_hours(_now()):
            return "DEFERRED: quiet hours (21:00-08:00) — do not text now."
        volunteer = next(
            v for v in store.volunteers() if v.volunteer_id == volunteer_id
        )
        shift = store.get_shift(shift_id)
        ok, reason = is_eligible(shift, volunteer)
        if not ok:
            return f"BLOCKED: {reason}."
        if store.asks_today(volunteer_id) >= _messaging.MAX_ASKS_PER_VOLUNTEER_PER_DAY:
            return f"BLOCKED: {volunteer.first_name} already asked cap times today."
        msg = channel.send(
            volunteer.phone, offer_text(volunteer.first_name, shift)
        )
        store.record_ask(campaign_id, volunteer_id, shift_id)
        store.add_receipt(
            campaign_id, "offer_sent",
            f"asked {volunteer.first_name} ({volunteer_id}): {msg.message_id}",
        )
        return msg.message_id

    @tool
    def check_reply(message_id: str, campaign_id: str, timeout_seconds: float = 60) -> str:
        """Wait for the volunteer's reply to a sent offer. Returns YES, NO, or TIMEOUT."""
        for sent in channel.sent:
            if sent.message_id == message_id:
                reply = channel.await_reply(sent, timeout_seconds)
                if reply is None:
                    store.add_receipt(campaign_id, "offer_timeout",
                                      f"{message_id} unanswered")
                    return "TIMEOUT"
                answer = parse_reply(reply.body)
                store.add_receipt(campaign_id, "offer_reply",
                                  f"{message_id} -> {answer}")
                return answer
        return "UNKNOWN_MESSAGE_ID"

    @tool
    def book_slot(shift_id: str, volunteer_id: str, campaign_id: str) -> str:
        """Lock a volunteer into a shift (atomic) and record the receipt.
        May pause for coordinator approval on sensitive bookings."""
        volunteer = next(
            v for v in store.volunteers() if v.volunteer_id == volunteer_id
        )
        try:
            updated = store.fill_slot(
                shift_id, campaign_id,
                f"{volunteer_id} ({volunteer.first_name}) accepted",
            )
        except (KeyError, ValueError) as e:
            return f"FAILED: {e}"
        if updated.gap:
            return f"BOOKED: {volunteer.first_name} on {shift_id}; {updated.gap} slot(s) still open."
        return f"BOOKED: {volunteer.first_name} on {shift_id}; shift now full."

    @tool
    def log_receipt(campaign_id: str, kind: str, detail: str) -> str:
        """Record an audit receipt (escalations, notes, deferrals)."""
        store.add_receipt(campaign_id, kind, detail)
        return "LOGGED"

    return [list_gaps, rank_candidates, send_offer, check_reply, book_slot, log_receipt]


def resolve_model():
    """Model portability: Anthropic > OpenAI > Bedrock default.

    The agent loop, tools, and interrupts are identical on every provider;
    only auth changes. WPILOT_MODEL_ID overrides the provider default.
    Bedrock bearer-token auth (mantle) is picked up from
    AWS_BEARER_TOKEN_BEDROCK automatically by the AWS SDK chain.
    """
    override = os.environ.get("WPILOT_MODEL_ID")
    if os.environ.get("ANTHROPIC_API_KEY"):
        from strands.models.anthropic import AnthropicModel

        kw = {"model_id": override} if override else {}
        return AnthropicModel(**kw)
    if os.environ.get("OPENAI_API_KEY"):
        from strands.models.openai import OpenAIModel

        kw = {"model_id": override} if override else {}
        return OpenAIModel(**kw)
    return None  # Strands Bedrock default (SigV4 or bearer chain)


def build_agent(
    store: Store,
    channel: SimulatedChannel,
    session_dir: str | Path,
    session_id: str = "wpilot-demo",
) -> Agent:
    """Construct the campaign agent with approval hook + persistent sessions,
    so a paused campaign (interrupt) survives process restarts."""
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, Any] = {}
    model = resolve_model()
    if model is not None:
        kwargs["model"] = model
    # model=None would override the Strands Bedrock default — omit instead.
    return Agent(
        system_prompt=SYSTEM_PROMPT,
        tools=build_tools(store, channel),
        hooks=[BookingApprovalHook(store)],
        session_manager=FileSessionManager(
            session_id=session_id, storage_dir=str(session_dir)
        ),
        callback_handler=None,
        **kwargs,
    )
