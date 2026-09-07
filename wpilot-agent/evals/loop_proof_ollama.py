"""Offline live-loop proof: real Strands agent (local model) over real tools.

Guided run (a local 8B model needs step-by-step prompts; frontier models
follow the single-prompt version — the loop, tools, interrupts, and session
resume are identical either way):

Phase A (process 1): agent works S1 step by step until book_slot(Alex,
low-reliability) raises an interrupt. Process EXITS at the interrupt.
Phase B (process 2): a fresh agent on the SAME session_dir answers the
interrupt and completes the booking.

Run from wpilot-agent/ (venv active, `ollama serve` running):
    export PATH=$HOME/.ollama-bin/bin:$PATH
    rm -f /tmp/opencode/wpilot-proof.db; rm -rf /tmp/opencode/wpilot-proof-sessions
    WPILOT_PROOF_MODEL=llama3.1:8b python evals/loop_proof_ollama.py A
    WPILOT_PROOF_MODEL=llama3.1:8b python evals/loop_proof_ollama.py B

Both phases append to /tmp/opencode/wpilot-proof-transcript.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DB = "/tmp/opencode/wpilot-proof.db"
SESS = "/tmp/opencode/wpilot-proof-sessions"
STATE = "/tmp/opencode/wpilot-proof-interrupts.json"
TRANSCRIPT = "/tmp/opencode/wpilot-proof-transcript.md"

SCRIPTED = {
    "+15550001001": "NO",  # Maya
    "+15550001008": "NO",  # Casey
    "+15550001002": "NO",  # Devon
    "+15550001006": "YES",  # Alex (0.43 -> approval interrupt)
}

STEPS = [
    "Call list_gaps. Reply with the open shift IDs, nothing else.",
    "Call rank_candidates with shift_id S1. Reply with the volunteer IDs in order, nothing else.",
    "Call send_offer with volunteer_id V1, shift_id S1, campaign_id PROOF-1. "
    "Then call check_reply with the returned message_id, campaign_id PROOF-1, "
    "timeout_seconds 5. Reply with the result word only.",
    "Call send_offer with volunteer_id V8, shift_id S1, campaign_id PROOF-1. "
    "Then call check_reply with the returned message_id, campaign_id PROOF-1, "
    "timeout_seconds 5. Reply with the result word only.",
    "Call send_offer with volunteer_id V2, shift_id S1, campaign_id PROOF-1. "
    "Then call check_reply with the returned message_id, campaign_id PROOF-1, "
    "timeout_seconds 5. Reply with the result word only.",
    "Call send_offer with volunteer_id V6, shift_id S1, campaign_id PROOF-1. "
    "Then call check_reply with the returned message_id, campaign_id PROOF-1, "
    "timeout_seconds 5. Reply with the result word only.",
    "Call book_slot with volunteer_id V6, shift_id S1, campaign_id PROOF-1. No other text.",
]


def log(line: str) -> None:
    print(line, flush=True)
    with open(TRANSCRIPT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


TOOLCALL_BUDGET = 12
_toolcall_count = 0


class _StepBudgetExceeded(Exception):
    pass


def reset_toolcall_budget() -> None:
    global _toolcall_count
    _toolcall_count = 0


def tracer(**kwargs) -> None:
    """Best-effort tool-call trace into the transcript (ground truth)."""
    global _toolcall_count
    event = kwargs.get("event", {}) or {}
    start = event.get("contentBlockStart", {}).get("start", {})
    if "toolUse" in start:
        _toolcall_count += 1
        tu = start["toolUse"]
        log(f"TOOLCALL {tu.get('name')} input={json.dumps(tu.get('input'))[:200]}")
        if _toolcall_count >= TOOLCALL_BUDGET:
            raise _StepBudgetExceeded(
                f"proof guard: {_toolcall_count} tool calls in one step")
    try:
        event = kwargs.get("event", {}) or {}
        start = event.get("contentBlockStart", {}).get("start", {})
        if "toolUse" in start:
            tu = start["toolUse"]
            log(f"TOOLCALL {tu.get('name')} input={json.dumps(tu.get('input'))[:200]}")
        delta = event.get("contentBlockDelta", {}).get("delta", {})
        if "toolResult" in delta:
            log(f"TOOLRESULT {json.dumps(delta['toolResult'])[:200]}")
        msg = event.get("message", {})
        if isinstance(msg, dict):
            for block in msg.get("content", []) or []:
                if "toolResult" in block:
                    log(f"TOOLRESULT {json.dumps(block['toolResult'])[:200]}")
    except Exception:
        pass


def make_agent():
    from strands.models.ollama import OllamaModel

    from wpilot.agent import build_agent
    from wpilot.messaging import SimulatedChannel
    from wpilot.store import Store

    import os
    from datetime import datetime

    model_id = os.environ.get("WPILOT_PROOF_MODEL", "qwen3:8b")
    store = Store(DB)
    if not store.shifts():
        store.import_csvs("seeds/shifts.csv", "seeds/volunteers.csv")
    channel = SimulatedChannel(dict(SCRIPTED))
    # NOTE: additional_args={"think": False} 500s this Ollama build, so
    # thinking stays on — the successful proof run used thinking anyway.
    model = OllamaModel(host="http://localhost:11434", model_id=model_id,
                        temperature=0)
    agent = build_agent(store, channel, SESS, session_id="proof", model=model,
                        now_fn=lambda: datetime(2026, 9, 9, 12, 0),
                        callback_handler=tracer)
    return agent, store


def show_text(result) -> str:
    try:
        text = ""
        content = result.message.get("content", []) if isinstance(result.message, dict) else []
        for block in content:
            text += block.get("text", "")
        return text[:400]
    except Exception:
        return "(unreadable)"


def phase_a() -> int:
    agent, store = make_agent()
    log("## Phase A — fresh process, guided steps, ends at approval interrupt")
    for i, step in enumerate(STEPS, 1):
        reset_toolcall_budget()
        try:
            result = agent(step)
        except _StepBudgetExceeded as e:
            log(f"--- step {i} BUDGET-EXCEEDED: {e} (moving to next step)")
            continue
        log(f"--- step {i} stop={result.stop_reason} text={show_text(result)!r}")
        for r in store.receipts("PROOF-1"):
            pass
        if result.stop_reason == "interrupt":
            saved = [
                {"id": x.id, "name": x.name, "reason": x.reason}
                for x in (result.interrupts or [])
            ]
            Path(STATE).write_text(json.dumps(saved), encoding="utf-8")
            for it in saved:
                log(f"INTERRUPT name={it['name']} reason={json.dumps(it['reason'])}")
            log("phase A exiting (process ends — resume is a NEW process)")
            return 0
    log("UNEXPECTED: steps exhausted without interrupt")
    return 1


def phase_b() -> int:
    agent, store = make_agent()
    log("## Phase B — NEW process, same session_dir, answers the interrupt")
    for rnd in range(1, 4):
        saved = json.loads(Path(STATE).read_text(encoding="utf-8"))
        interrupt_id = saved[0]["id"]
        log(f"--- resume round {rnd}: approving {saved[0]['name']} + trust")
        result = agent([{
            "interruptResponse": {"interruptId": interrupt_id, "response": "t"}
        }])
        log(f"stop_reason={result.stop_reason} text={show_text(result)!r}")
        if result.stop_reason != "interrupt":
            break
        saved = [
            {"id": x.id, "name": x.name, "reason": x.reason}
            for x in (result.interrupts or [])
        ]
        Path(STATE).write_text(json.dumps(saved), encoding="utf-8")
        for it in saved:
            log(f"INTERRUPT name={it['name']} reason={json.dumps(it['reason'])[:160]}")
    for r in store.receipts("PROOF-1"):
        log(f"receipt [{r['kind']}] {r['detail'][:100]}")
    s = store.get_shift("S1")
    log(f"S1 now: {s.slots_filled}/{s.slots_needed} filled")
    return 0 if s.gap == 0 else 1


if __name__ == "__main__":
    raise SystemExit(phase_a() if sys.argv[1] == "A" else phase_b())
