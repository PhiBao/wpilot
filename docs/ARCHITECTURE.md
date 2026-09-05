# wpilot — architecture

```mermaid
flowchart LR
    subgraph volunteer ["Volunteer (SMS, no account)"]
        SMS["texts YES / NO"]
    end
    subgraph coord ["Coordinator (web, mobile-friendly)"]
        UI["console: shifts · needs-you · receipts"]
        DEMO["demo console: simulated phone"]
    end
    subgraph api ["Demo API — FastAPI (Fly.io, one warm machine)"]
        S["server.py\nREST + interactive inbox"]
        E["campaign.py\nranked offers → timeout → book / escalate"]
        P["policy.py\ndeny-by-default eligibility"]
        DB[("SQLite\nroster + receipts")]
    end
    subgraph agent ["Strands agent loop (Bedrock at runtime)"]
        A["agent.py\n6 tools + BookingApprovalHook"]
        INT{"interrupt?\nlow-reliability / restricted role"}
    end

    SMS --> S
    UI --> S
    DEMO --> S
    S --> E --> P
    E --> DB
    S --> A
    A --> E
    A --> INT
    INT -->|yes| coord
```

## Components

| Piece | What it does | Where |
|---|---|---|
| Console `/` | Shift cards, needs-you queue, receipt feed | `wpilot-ui/app/page.tsx` → Vercel |
| Demo console `/demo` | Simulated phone + trigger + reset | `wpilot-ui/app/demo/page.tsx` |
| Confirm `/confirm/[id]` | No-login volunteer accept page | `wpilot-ui/app/confirm/` |
| Demo API | Shifts, campaigns, inbox, offers, reset, agent run/answer | `wpilot-agent/src/wpilot/server.py` → Fly.io |
| Campaign engine | Deterministic backfill loop; safety rails enforced here, never in the prompt | `campaign.py` + `messaging.py` |
| Policy | Eligibility, adults-only default, ranking | `policy.py` (Cedar-shaped rules; Cedar-backed next) |
| Agent loop | Proposes; tools dispose; hook interrupts on judgment calls; sessions persist across restarts | `agent.py` (Strands) |
| Evals | 10 product-guarantee scenarios → `evals/report.md` | `wpilot-agent/evals/` |

## Key decisions

- **Deterministic core, agentic edge.** Schedule math, eligibility, dedupe,
  atomic booking, quiet hours, and ask caps are code. The LLM proposes order
  and wording, and handles the unexpected — it can never widen who gets
  texted or what gets booked.
- **Interrupts are the product.** `stop_reason == "interrupt"` + session
  persistence is how "runs in the background, surfaces when a human must
  decide" is implemented — not a chatbot with extra steps.
- **Receipts over dashboards.** Every action appends an immutable receipt;
  the coordinator UI is a clipboard, not a portal.
- **Demo honesty.** The simulated SMS channel is a real channel boundary:
  the engine cannot distinguish it from a real provider. Nothing is canned.
```

