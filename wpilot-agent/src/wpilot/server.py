"""wpilot demo server: REST API over the campaign engine + Strands agent.

Single-process demo service (documented limitation, not a production claim):
- SQLite roster store, reseeded on demand
- InteractiveChannel: the demo console / volunteer confirm page posts replies
- One campaign at a time (409 while busy)
- /api/agent/* invokes the live Strands loop and needs Bedrock credentials
  at runtime; without them it answers 503 honestly.

Run: uvicorn wpilot.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import build_agent
from .campaign import CampaignResult, Engine
from .messaging import InteractiveChannel
from .store import Store

SEEDS_DIR = Path(__file__).resolve().parent.parent.parent / "seeds"
SESSIONS_DIR = Path(__file__).resolve().parent.parent.parent / "sessions"


def _now() -> datetime:
    """Injectable clock: WPILOT_CLOCK (ISO) pins time in tests/demos."""
    import os

    raw = os.environ.get("WPILOT_CLOCK")
    return datetime.fromisoformat(raw) if raw else datetime.now()

app = FastAPI(title="wpilot demo API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo only; lock down for any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


class DemoState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.campaign_busy = False
        self.campaigns: list[dict[str, Any]] = []
        self.agent_runs: dict[str, dict[str, Any]] = {}
        self.reset()

    def reset(self) -> None:
        self.store = Store()
        self.store.import_csvs(SEEDS_DIR / "shifts.csv", SEEDS_DIR / "volunteers.csv")
        self.channel = InteractiveChannel()
        self.campaigns = []
        self.agent_runs = {}
        self.campaign_busy = False


STATE = DemoState()


def result_to_dict(r: CampaignResult) -> dict[str, Any]:
    return {
        "campaign_id": r.campaign_id, "shift_id": r.shift_id,
        "outcome": r.outcome, "accepted_by": r.accepted_by,
        "needs_review": r.needs_review, "reason": r.reason, "asked": r.asked,
    }


class RunCampaign(BaseModel):
    shift_id: str
    reply_timeout_seconds: float = 60.0


class PostReply(BaseModel):
    body: str


class UndoBooking(BaseModel):
    shift_id: str


class AgentRun(BaseModel):
    prompt: str


class AgentAnswer(BaseModel):
    responses: list[dict[str, Any]]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/debug/provider")
def debug_provider() -> dict[str, Any]:
    """Presence flags only — no secret values. Tells us which model path
    the agent loop will take in THIS container."""
    import os

    from .agent import resolve_model

    try:
        model = resolve_model()
        provider = type(model).__name__ if model is not None else "bedrock-default"
    except Exception as e:  # noqa: BLE001
        return {"provider": f"resolve-error: {type(e).__name__}: {e}"}
    return {
        "provider": provider,
        "has_mantle_key": bool(os.environ.get("BEDROCK_SERVICE_SECRET")),
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
        "model_override": os.environ.get("WPILOT_MODEL_ID", ""),
    }


@app.get("/api/shifts")
def shifts() -> list[dict[str, Any]]:
    out = []
    for s in STATE.store.shifts():
        status = "covered" if s.gap <= 0 else "open"
        out.append({
            "shift_id": s.shift_id, "date": s.date,
            "window": f"{s.start_time}-{s.end_time}", "role": s.role,
            "slots_needed": s.slots_needed, "slots_filled": s.slots_filled,
            "gap": s.gap, "location": s.location,
            "eligibility": sorted(s.eligibility_tags), "status": status,
        })
    return out


@app.get("/api/campaigns")
def campaigns() -> list[dict[str, Any]]:
    return STATE.campaigns


@app.post("/api/campaigns", status_code=201)
def run_campaign(req: RunCampaign) -> dict[str, Any]:
    with STATE.lock:
        if STATE.campaign_busy:
            raise HTTPException(409, "a campaign is already running")
        STATE.campaign_busy = True
    try:
        try:
            STATE.store.get_shift(req.shift_id)
        except KeyError:
            raise HTTPException(404, f"unknown shift {req.shift_id}")
        engine = Engine(
            STATE.store, STATE.channel, reply_timeout_seconds=req.reply_timeout_seconds,
            now=_now(),
        )
        result = engine.run_for_shift(req.shift_id)
    finally:
        with STATE.lock:
            STATE.campaign_busy = False
    record = result_to_dict(result)
    record["receipts"] = STATE.store.receipts(result.campaign_id)
    STATE.campaigns.append(record)
    return record


@app.post("/api/campaigns/{campaign_id}/undo")
def undo_campaign_booking(campaign_id: str, req: UndoBooking) -> dict[str, Any]:
    try:
        updated = STATE.store.undo_booking(campaign_id, req.shift_id)
    except (KeyError, ValueError) as e:
        raise HTTPException(404, str(e))
    for record in STATE.campaigns:
        if record["campaign_id"] == campaign_id:
            record["receipts"] = STATE.store.receipts(campaign_id)
    return {"ok": True, "shift_id": updated.shift_id,
            "slots_filled": updated.slots_filled, "gap": updated.gap}


@app.get("/api/inbox")
def inbox() -> list[dict[str, Any]]:
    return [
        {"message_id": m.message_id, "to": m.to_phone, "body": m.body,
         "meta": m.meta, "reply": STATE.channel.reply_for(m.message_id)}
        for m in STATE.channel.sent
    ]


@app.post("/api/inbox/reply")
def inbox_reply(message_id: str, req: PostReply) -> dict[str, bool]:
    ok = STATE.channel.post_reply(message_id, req.body)
    if not ok:
        raise HTTPException(404, f"unknown message {message_id}")
    return {"ok": True}


@app.get("/api/offers/{message_id}")
def offer(message_id: str) -> dict[str, Any]:
    for m in STATE.channel.sent:
        if m.message_id == message_id:
            shift = None
            if m.meta.get("shift_id"):
                try:
                    s = STATE.store.get_shift(m.meta["shift_id"])
                    shift = {"shift_id": s.shift_id, "date": s.date,
                             "window": f"{s.start_time}-{s.end_time}",
                             "role": s.role, "location": s.location}
                except KeyError:
                    shift = None
            return {"message_id": m.message_id, "body": m.body,
                    "meta": m.meta, "shift": shift,
                    "reply": STATE.channel.reply_for(m.message_id)}
    raise HTTPException(404, f"unknown message {message_id}")


@app.post("/api/offers/{message_id}/answer")
def answer_offer(message_id: str, req: PostReply) -> dict[str, bool]:
    return inbox_reply(message_id, req)


@app.get("/api/receipts")
def receipts(campaign_id: str = "") -> list[dict[str, Any]]:
    return STATE.store.receipts(campaign_id)


@app.post("/api/demo/reset")
def demo_reset() -> dict[str, bool]:
    with STATE.lock:
        STATE.reset()
    return {"ok": True}


def _agent_payload(run_id: str, result: Any) -> dict[str, Any]:
    if result.stop_reason == "interrupt":
        STATE.agent_runs[run_id] = {"result": result}
        return {
            "run_id": run_id, "status": "needs_input",
            "interrupts": [
                {"id": i.id, "name": i.name, "reason": i.reason}
                for i in (result.interrupts or [])
            ],
        }
    STATE.agent_runs.pop(run_id, None)
    message = result.message
    text = ""
    try:
        for block in message.get("content", []):
            text += block.get("text", "")
    except Exception:
        text = str(message)
    return {"run_id": run_id, "status": "done", "message": text}


@app.post("/api/agent/run", status_code=201)
def agent_run(req: AgentRun) -> dict[str, Any]:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    agent = build_agent(STATE.store, STATE.channel, session_dir=SESSIONS_DIR)
    run_id = f"run-{len(STATE.agent_runs) + 1}"
    try:
        result = agent(req.prompt)
    except Exception as e:  # e.g. no Bedrock credentials in this environment
        raise HTTPException(
            503, f"agent loop unavailable here ({type(e).__name__}: {e}). "
                 "Run with AWS Bedrock credentials, or use /api/campaigns "
                 "for the deterministic engine path."
        )
    return _agent_payload(run_id, result)


@app.post("/api/agent/answer")
def agent_answer(run_id: str, req: AgentAnswer) -> dict[str, Any]:
    saved = STATE.agent_runs.get(run_id)
    if saved is None:
        raise HTTPException(404, f"unknown or finished run {run_id}")
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    agent = build_agent(STATE.store, STATE.channel, session_dir=SESSIONS_DIR)
    try:
        result = agent(req.responses)
    except Exception as e:
        raise HTTPException(503, f"agent loop unavailable here ({e})")
    return _agent_payload(run_id, result)
