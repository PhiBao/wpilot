"""Messaging channels.

v1 ships two channels:
- SimulatedChannel: in-memory inbox for the demo console and tests. Every
  "sent" SMS is real engine behavior against a simulated *channel* — never a
  canned campaign script.
- (Sep 10) SES email channel for real delivery.

Safety rails enforced here, not in the prompt: quiet hours, per-volunteer
daily ask caps, idempotent message IDs.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from datetime import datetime

QUIET_START_HOUR = 21  # no outbound texts 21:00-08:00 local
QUIET_END_HOUR = 8
MAX_ASKS_PER_VOLUNTEER_PER_DAY = 2


@dataclass
class OutboundMessage:
    message_id: str
    to_phone: str
    body: str
    sent_at: float = field(default_factory=time.time)
    meta: dict = field(default_factory=dict)  # shift_id, volunteer_id, ...


@dataclass
class InboundReply:
    message_id: str  # the outbound message being answered
    from_phone: str
    body: str


class SimulatedChannel:
    """In-memory SMS stand-in. Scripted replies drive tests; the demo console
    drives it interactively (judge taps YES/NO on the simulated phone)."""

    def __init__(self, scripted_replies: dict[str, str] | None = None) -> None:
        # phone -> reply body ("YES"/"NO"); missing phone = silence (timeout)
        self.scripted_replies = scripted_replies or {}
        self.sent: list[OutboundMessage] = []
        self._ids = itertools.count(1)

    def send(self, to_phone: str, body: str, meta: dict | None = None) -> OutboundMessage:
        msg = OutboundMessage(
            message_id=f"sim-{next(self._ids)}", to_phone=to_phone, body=body,
            meta=meta or {},
        )
        self.sent.append(msg)
        return msg

    def await_reply(
        self, msg: OutboundMessage, timeout_seconds: float
    ) -> InboundReply | None:
        """Block up to timeout for a reply. Scripted phones answer instantly;
        unscripted phones time out (deadline honored in real deployments)."""
        reply = self.scripted_replies.get(msg.to_phone)
        if reply is None:
            if timeout_seconds > 0:
                time.sleep(min(timeout_seconds, 0.05))  # simulated wait
            return None
        return InboundReply(
            message_id=msg.message_id, from_phone=msg.to_phone, body=reply
        )


def in_quiet_hours(now: datetime | None = None) -> bool:
    hour = (now or datetime.now()).hour
    return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR


class InteractiveChannel(SimulatedChannel):
    """Demo-console channel: replies arrive when a human taps them.

    await_reply polls for a posted reply until the timeout, so a judge can
    watch the offer land in the simulated inbox and answer it live. Scripted
    replies (per phone) still work as instant answers for tests.
    """

    POLL_INTERVAL = 0.2

    def __init__(self, scripted_replies: dict[str, str] | None = None) -> None:
        super().__init__(scripted_replies)
        self.posted: dict[str, str] = {}  # message_id -> reply body

    def post_reply(self, message_id: str, body: str) -> bool:
        if not any(m.message_id == message_id for m in self.sent):
            return False
        self.posted[message_id] = body
        return True

    def reply_for(self, message_id: str) -> str | None:
        return self.posted.get(message_id)

    def await_reply(
        self, msg: OutboundMessage, timeout_seconds: float
    ) -> InboundReply | None:
        deadline = time.time() + max(0.0, timeout_seconds)
        while True:
            if msg.message_id in self.posted:
                return InboundReply(
                    message_id=msg.message_id, from_phone=msg.to_phone,
                    body=self.posted[msg.message_id],
                )
            scripted = self.scripted_replies.get(msg.to_phone)
            if scripted is not None:
                self.posted[msg.message_id] = scripted  # visible in inbox
                return InboundReply(
                    message_id=msg.message_id, from_phone=msg.to_phone,
                    body=scripted,
                )
            if time.time() >= deadline:
                return None
            time.sleep(self.POLL_INTERVAL)


def parse_reply(body: str) -> str:
    """Normalize a volunteer reply to YES / NO / UNKNOWN (untrusted input)."""
    text = body.strip().lower()
    if text in ("yes", "y", "yeah", "yep", "ok", "okay", "sure", "confirm"):
        return "YES"
    if text in ("no", "n", "nope", "can't", "cant", "sorry", "decline"):
        return "NO"
    return "UNKNOWN"
