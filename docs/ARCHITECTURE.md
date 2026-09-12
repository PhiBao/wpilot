# wpilot — architecture

```mermaid
flowchart TB
  subgraph people["People"]
    V["Volunteer<br/>texts YES / NO<br/>no account"]
    C["Coordinator<br/>one clipboard page"]
    J["Judge / demo console<br/>simulated phone"]
  end

  subgraph ui["UI — Next.js on Vercel"]
    CONSOLE["Console<br/>shifts · needs-you · receipts"]
    DEMO["Demo console<br/>trigger + tap replies"]
    CONFIRM["Confirm page<br/>no-login accept link"]
  end

  subgraph service["wpilot API — Python · FastAPI on AWS App Runner"]
    SRV["REST API<br/>+ interactive inbox"]
    ENG["Campaign engine<br/>rank offers → timeout → next"]
    POL["Eligibility policy<br/>deny-by-default"]
    MSG["Messaging channel<br/>simulated SMS + email path"]
    DB[("SQLite<br/>roster · offers · replies<br/>receipts · snapshots")]
  end

  subgraph agent["Strands agent loop — Amazon Bedrock via mantle"]
    TOOLS["8 tools<br/>gaps · rank · offer · reply<br/>book · receipts · read · undo"]
    HOOK["BookingApprovalHook"]
    INT{"Interrupt?"}
    SESS["FileSessionManager<br/>trust + resume across restarts"]
  end

  subgraph infra["AWS infrastructure"]
    ECR["ECR"]
    CWL["CloudWatch"]
    AC["AgentCore Runtime<br/>deploy target · quota pending"]
  end

  V --> MSG
  C --> CONSOLE
  J --> DEMO
  CONSOLE --> SRV
  DEMO --> SRV
  CONFIRM --> SRV
  SRV --> ENG
  ENG --> POL
  ENG --> MSG
  SRV <--> TOOLS
  TOOLS --> ENG
  TOOLS --> HOOK
  HOOK --> INT
  INT -->|yes, one card| CONSOLE
  HOOK -. persists .- SESS
  ENG --> DB
  TOOLS --> DB
  SRV -. image .-> ECR
  SRV -. logs .-> CWL
  TOOLS -. deploy target .-> AC

  classDef person fill:#e5f3ea,stroke:#1e7f43,color:#1c1a16
  classDef ui fill:#e8eefc,stroke:#2456d6,color:#1c1a16
  classDef api fill:#fdf1d7,stroke:#9a6200,color:#1c1a16
  classDef agentc fill:#f3e8fc,stroke:#7a3cc4,color:#1c1a16
  classDef infrac fill:#ececec,stroke:#666,color:#1c1a16

  class V,C,J person
  class CONSOLE,DEMO,CONFIRM ui
  class SRV,ENG,POL,MSG,DB api
  class TOOLS,HOOK,INT,SESS agentc
  class ECR,CWL,AC infrac
```

(A rendered PNG of this diagram is provided with the Devpost submission
materials; the mermaid above renders natively on GitHub.)

## Components

| Piece | What it does | Where |
|---|---|---|
| Console `/` | Shift cards, needs-you queue, receipt feed (incl. live-agent runs) | `wpilot-ui/app/page.tsx` → Vercel |
| Demo console `/demo` | Simulated phone + cancellation trigger + reset | `wpilot-ui/app/demo/page.tsx` |
| Confirm `/confirm/[id]` | No-login volunteer accept page | `wpilot-ui/app/confirm/` |
| API | Shifts, campaigns, inbox, offers, reset, receipts, agent run/answer | `wpilot-agent/src/wpilot/server.py` → App Runner |
| Campaign engine | Deterministic backfill loop; safety rails enforced here, never in the prompt | `campaign.py` + `messaging.py` |
| Policy | Eligibility, adults-only default, ranking | `policy.py` (Cedar-shaped rules; Cedar-backed next) |
| Agent loop | 8 tools; proposes, tools dispose; hook interrupts on judgment calls; sessions persist across restarts | `agent.py` (Strands) |
| Evals | 15 product-guarantee + trajectory scenarios → `evals/report.md` | `wpilot-agent/evals/` |

## Key decisions

- **Deterministic core, agentic edge.** Schedule math, eligibility, dedupe,
  atomic booking, quiet hours, ask caps, and consent verification are code.
  The LLM proposes order and wording and handles the unexpected — it can
  never widen who gets texted or what gets booked.
- **Interrupts are the product.** `stop_reason == "interrupt"` + session
  persistence is how "runs in the background, surfaces when a human must
  decide" is implemented — not a chatbot with extra steps.
- **Receipts over dashboards.** Every action appends an immutable receipt;
  the coordinator UI is a clipboard, not a portal.
- **Demo honesty.** The simulated SMS channel is a real channel boundary:
  the engine cannot distinguish it from a real provider. Nothing is canned.
