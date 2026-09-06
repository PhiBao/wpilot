"""AgentCore Runtime entrypoint: the wpilot campaign agent as a service.

Contract: linux/arm64 image, /invocations + /ping on 8080 (provided by
BedrockAgentCoreApp). Payload: {"prompt": ..., "session_id": ...}.
Response: {"status": "done", "message": ...} or
{"status": "needs_input", "session_id": ..., "interrupts": [...]}.
Resume: {"session_id": ..., "responses": [{"interruptResponse": ...}]}.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from .agent import build_agent
from .messaging import InteractiveChannel
from .store import Store

BASE = Path(__file__).resolve().parent.parent.parent
SEEDS = BASE / "seeds"
SESSIONS = BASE / "sessions"

app = BedrockAgentCoreApp()


def _agent(session_id: str):
    SESSIONS.mkdir(parents=True, exist_ok=True)
    store = Store()
    store.import_csvs(SEEDS / "shifts.csv", SEEDS / "volunteers.csv")
    return build_agent(store, InteractiveChannel(), SESSIONS, session_id)


@app.entrypoint
def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    session_id = str(payload.get("session_id", "wpilot-agentcore"))
    agent = _agent(session_id)
    if "responses" in payload:
        result = agent(payload["responses"])
    else:
        result = agent(str(payload.get("prompt", "List open gaps and fill the most urgent one.")))
    if result.stop_reason == "interrupt":
        return {
            "status": "needs_input",
            "session_id": session_id,
            "interrupts": [
                {"id": i.id, "name": i.name, "reason": i.reason}
                for i in (result.interrupts or [])
            ],
        }
    text = ""
    try:
        for block in result.message.get("content", []):
            text += block.get("text", "")
    except Exception:
        text = str(result.message)
    return {"status": "done", "session_id": session_id, "message": text}


if __name__ == "__main__":
    app.run()
