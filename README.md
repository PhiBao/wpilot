# wpilot — the backfill agent for volunteer-run shifts

> When a shift goes short, wpilot works the phone tree — texts the right
> volunteers, locks in a commitment, updates the roster — and only interrupts
> the coordinator when a human actually needs to decide.

Built for the **Agents for Humans** hackathon (Good Neighbor track) with the
[Strands Agents SDK](https://strandsagents.com/).

**Live demo:** https://wpilot-ui.vercel.app · **Demo console:** https://wpilot-ui.vercel.app/demo
**Live API:** https://fpxyvjfpc5.us-east-1.awsapprunner.com · **Demo video:** 3½-min narrated walkthrough (uploaded to YouTube for submission)
**Evals:** `wpilot-agent/evals/report.md` (15/15) · **License:** MIT

---

## Why — the problem

Every week, at thousands of food pantries, shelters, and community programs,
the same scene plays out. Someone cancels a volunteer shift, and the
coordinator — usually one overloaded staffer or a super-volunteer — spends the
evening texting people one by one from a personal phone until the hole is
filled. The numbers behind that evening are brutal:

- **~1 in 4** scheduled volunteers no-show; **30%** don't return after year one.
- Coordinators report personally replying to **~50 volunteers a week** and
  copying answers into a spreadsheet.
- **67%** of volunteer programs have no waitlist management at all — a
  cancellation is simply a gap.
- The top no-show causes are mundane and automatable: forgotten shifts (38%),
  late-discovered conflicts (27%), missing reminders (22%).

Existing volunteer software sells **portals and reminders**: volunteers must
log in, coordinators must check dashboards. But nobody logs in, and the
coordinator has no time to check. The work that actually matters — *the
chase*: noticing the gap, working the waitlist, negotiating, confirming,
updating the roster — is still 100% manual. Paid-staffing tools sell
autonomous backfill (Shiftboard, clinic "5-minute backfill" products). For
volunteer-run orgs, that product **does not exist**. That's the gap wpilot fills.

The trust angle matters as much as the labor angle. Coordinators place people
in front of vulnerable populations. An agent that acts without an auditable
record of who was asked, what was said, and who accepted is unadoptable —
consumer research keeps confirming it: people accept low-autonomy help (86%)
far more than high-autonomy action (52%), and adoption hinges on transparency
and available human oversight. So wpilot is designed as a **supervised agent**:
it does the chasing, receipts everything, and interrupts exactly when judgment
is required.

## What — the product

wpilot watches an org's shift roster. When a shift goes short — a cancellation
comes in, or a scan finds unfilled slots — it runs a **backfill campaign**:

1. **Ranks** eligible volunteers (training tags, adults-only policy, availability
   overlap, response history).
2. **Texts them one by one** with a human-quality offer ("Can you cover Thu 9am
   packing? Reply YES or NO"), waits, moves on after NO/silence.
3. **Books the first YES** — atomically, into the roster — sends a confirmation,
   and posts a **receipt**: who was asked, what was said, who accepted.
4. **Interrupts the coordinator only** when a human must decide: the pool is
   exhausted, the acceptance came from a low-reliability volunteer, or the role
   is restricted. One tap answers; the campaign resumes.

The coordinator's experience is a text thread and **one clipboard page** — shift
cards, a needs-you queue, an activity feed of receipts. Volunteers never see an
account, an app, or a login: they answer texts, or tap a single-use confirm
link. Setup is a CSV upload (or one click on the seeded demo org).

**The unit of value: one gap filled with zero coordinator touches.**

## How — architecture and engineering choices

```
volunteer (SMS, no account) ──texts YES/NO──▶ FastAPI demo API ──▶ campaign engine
coordinator (web clipboard) ──Fill it / answers──▶     │              │ deterministic:
demo console (simulated phone) ──live taps──▶          │              │ policy, quiet hours,
                                                       │              │ ask caps, atomic booking
                                                       ▼              ▼
                                              Strands agent loop ◀── tools (gaps, rank,
                                              7 tools + approval │    offer, reply, book,
                                              hook + interrupts │    receipts, undo)
                                              session persistence │
                                                                  ▼
                                                       SQLite (roster, receipts,
                                                       offers, replies, snapshots)
```

Three principles run through every file:

1. **Deterministic core, agentic edge.** Schedule math, eligibility, quiet
   hours, ask caps, dedupe, and atomic booking are *code*. The model proposes
   order and wording and handles the unexpected — it can never widen who gets
   texted or what gets booked. `book_slot` REFUSEs without a durably recorded
   volunteer YES (enforced against the offers/replies tables, so it holds
   across processes); `log_receipt` allowlists its audit taxonomy.
2. **Interrupts are the product, not a feature.** `stop_reason == "interrupt"`
   plus a session manager is how "runs in the background, surfaces when a
   human must decide" is implemented. Booking approvals (`y` once / `t` trust /
   deny-with-reason), trust persisted in agent state, campaigns resumable
   after a process restart. Proven end-to-end in `docs/LOOP-PROOF.md`, including
   a kill-and-resume across processes.
3. **Receipts over dashboards.** Every action appends an immutable receipt; the
   UI is a clipboard, not a portal. The demo's simulated SMS channel is a real
   channel boundary — the engine cannot distinguish it from a provider, so
   nothing in the demo is canned.

### How Strands is used (Technical Implementation map)

| Strands capability | Where in wpilot | Evidence |
|---|---|---|
| Agent loop + custom tools | `agent.py` — 8 tools (gaps, ranking, offers, replies, booking, receipts, read-receipts, undo) | `tests/test_agent.py`, live `/demo` |
| Hook interrupts (`BeforeToolCallEvent`) | `BookingApprovalHook` gates `book_slot` on low-reliability / restricted bookings | `approval_decision` + `interpret_approval_response` tests |
| Session-managed interrupts | `FileSessionManager` + trust in agent state — paused campaigns survive restarts | `build_agent`, `docs/LOOP-PROOF.md` kill-and-resume |
| Snapshots / undo | Pre-booking snapshots, single-consume revert, fully receipted | `store.undo_booking`, UI "Undo booking" |
| Model portability | `resolve_model()`: Anthropic → OpenAI → Bedrock mantle → Bedrock default | Live on mantle (`ministral-3-8b`); Ollama fallback for offline proofs |
| Safety outside the model | Policy, quiet hours, ask caps, consent verification, atomic writes | `evals/report.md` 15/15 |
| Multi-surface, one loop | Same tools serve console, demo phone, confirm page, API | `server.py` (`/api/agent/*` runs the live loop publicly) |

Live model loop: `docs/LOOP-PROOF.md` — real Strands agent over a hosted model
(Bedrock mantle), declines → YES → approval interrupt → new process resumes
with trust → consent re-verified from durable tables → shift filled, round 1.

## Vision & roadmap

**Thesis.** Every volunteer shift program already pays for an "outreach
coordinator" — in salary or in a volunteer's evenings. An agent that does the
chase reliably, auditably, and cheaply doesn't compete with volunteer software;
it replaces a salary line nobody can afford. The wedge is backfill; the moat
is the per-volunteer reliability/availability memory plus the roster that
accumulates in wpilot.

**Now (hackathon entry, this repo).** One org, CSV roster, simulated SMS +
real email path, deterministic campaign engine + live Strands loop, interrupt
escalations, undo, evals, live demo. Validation target: a judge triggers a
cancellation cold and watches a fill in under two minutes.

**Next — pilots (5 pantries, success-gated).** Real SMS via a registered
provider (A2P 10DLC), Google Sheets as roster source of truth, Cedar policies
replacing the rules module 1:1, per-org quiet hours and branding. Metrics that
decide whether it continues: median time-to-fill < 30 min, median coordinator
touches per fill = 0, campaign acceptance ≥ 50%, escalation < 25%.

**Later — network.** Volunteers serve multiple orgs; reliability memory
portable across them (opt-in) makes every new org's backfill better on day
one. Pantry networks (e.g. Feeding America's 200 food banks → 60k pantries)
distribute top-down what coordinators already spread bottom-up. Pricing:
$30–100/mo per org, free under ~50 volunteers — matched to avoided coordinator
hours, insulated from platform risk because the workflow (outreach +
commitment + audit) is owned, not the conversation.

**Explicit non-goals.** No beneficiary data, ever. No background checks, hour
tracking, or self-scheduling portals in v1 — those are solved problems; the
chase is not.

---

## Quickstart

```bash
cd wpilot-agent && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q            # 34 passed
python -m evals.run_evals      # 15/15 scenarios passed
uvicorn wpilot.server:app --port 8000   # demo API
```

```bash
cd wpilot-ui && pnpm install
NEXT_PUBLIC_WPILOT_API=http://localhost:8000 pnpm dev   # console + demo
```

Model for the live loop: set `BEDROCK_SERVICE_SECRET` (Bedrock mantle bearer
key) — or `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — and `/api/agent/*` runs the
real Strands loop. Without keys, `/api/campaigns` runs the deterministic
engine path (same safety rails, no LLM).

## Layout

- `wpilot-agent/` — Python service: campaign engine, policy, messaging,
  receipts, Strands agent with approval interrupts, FastAPI demo server,
  evals (`evals/report.md`), loop proof (`docs/LOOP-PROOF.md`).
- `wpilot-ui/` — Next.js console `/`, demo console `/demo`, no-login
  volunteer page `/confirm/[messageId]`.
- `docs/` — `ARCHITECTURE.md` (diagram + components) · `LOOP-PROOF.md`
  (live agent loop transcript) · `DEPLOY.md` (runbook).
- `deploy/` — `agentcore_deploy.py` (Bedrock AgentCore, quota-pending),
  `apprunner_env.py` (runtime env without redeploy).
- `Dockerfile.api` / `Dockerfile.agentcore` / `fly.toml` — container targets.

## Status

Live: UI on Vercel, API on App Runner, evals green, loop proven on a hosted
model. Remaining: video upload, Devpost submit, builder posts, AWS-side
unblocks (account verification → Bedrock SigV4 + AgentCore quota). See
`docs/DEPLOY.md`.

License: MIT.
