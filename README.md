# wpilot

The backfill agent for volunteer-run shifts. When a shift goes short, wpilot works
the phone tree — texts the right volunteers, locks in a commitment, updates the
roster — and only interrupts the coordinator when a human actually needs to decide.

Built for the **Agents for Humans** hackathon (Good Neighbor track) with the
[Strands Agents SDK](https://strandsagents.com/).

**Live demo:** https://wpilot-ui.vercel.app · **Demo console:** https://wpilot-ui.vercel.app/demo
**Live API:** https://fpxyvjfpc5.us-east-1.awsapprunner.com/api/health (App Runner, us-east-1)

## Layout

- `wpilot-agent/` — Python service: campaign engine, policy, messaging, receipts,
  Strands agent with approval interrupts, FastAPI demo server, evals.
  Quickstart in `wpilot-agent/README.md`. Eval report: `wpilot-agent/evals/report.md` (10/10).
- `wpilot-ui/` — Next.js console: coordinator page `/`, demo console `/demo`,
  no-login volunteer page `/confirm/[messageId]`. Quickstart in `wpilot-ui/README.md`.
- `docs/` — `ARCHITECTURE.md` (diagram) · `SUBMISSION.md` (Devpost text) ·
  `VIDEO-SCRIPT.md` · `BUILDER-POST.md` (bonus-post draft) · `DEPLOY.md` (runbook).
- `Dockerfile.api` + `fly.toml` — demo API image (verified locally).

## How Strands is used (Technical Implementation map)

| Strands capability | Where in wpilot | Evidence |
|---|---|---|
| Agent loop + custom tools | `agent.py` — 7 tools (gaps, ranking, offers, replies, booking, receipts, undo) | `tests/test_agent.py`, live `/demo` |
| Hook interrupts (`BeforeToolCallEvent`) | `BookingApprovalHook` gates `book_slot` on low-reliability / restricted bookings | `approval_decision` + `interpret_approval_response` unit tests |
| Session-managed interrupts | `FileSessionManager` + trust in agent state — paused campaigns survive restarts | `build_agent`, kill-and-resume proof (see below) |
| Multi-surface, one loop | Same tools serve console, demo phone, confirm page, API | `server.py` |
| Snapshots / undo | Pre-booking snapshots, single-consume revert, fully receipted | `store.undo_booking`, UI "Undo booking", eval `audit-completeness` |
| Model portability | `resolve_model()`: Anthropic → OpenAI → Bedrock (SigV4 or bearer) → Ollama | provider tests |
| Deterministic safety outside the model | Policy, quiet hours, ask caps, atomic writes are code, not prompt | `evals/report.md` 15/15 |

Loop proofs: `python -m evals.run_evals` (15/15) · live demo above ·
 transcripts in `docs/LOOP-PROOF.md` (real model loop incl. an interrupt
round-trip and a kill-and-resume across processes).

## One-command checks

```bash
cd wpilot-agent && source .venv/bin/activate
python -m pytest -q            # 27 passed
python -m evals.run_evals      # 10/10 scenarios passed
```

## Status

Working entry: engine + policy + interrupts + API + UI + evals, all verified.
Remaining (needs human clicks): Fly API deploy + Vercel env update, video
recording, Devpost submit, AWS credits form (by Sep 11). See `docs/DEPLOY.md`.

License: MIT.
