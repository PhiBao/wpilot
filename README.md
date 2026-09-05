# wpilot

The backfill agent for volunteer-run shifts. When a shift goes short, wpilot works
the phone tree — texts the right volunteers, locks in a commitment, updates the
roster — and only interrupts the coordinator when a human actually needs to decide.

Built for the **Agents for Humans** hackathon (Good Neighbor track) with the
[Strands Agents SDK](https://strandsagents.com/).

**Live demo:** https://wpilot-ui.vercel.app · **Demo console:** https://wpilot-ui.vercel.app/demo
*(the demo console points at the API URL in `NEXT_PUBLIC_WPILOT_API`; see `docs/DEPLOY.md`)*

## Layout

- `wpilot-agent/` — Python service: campaign engine, policy, messaging, receipts,
  Strands agent with approval interrupts, FastAPI demo server, evals.
  Quickstart in `wpilot-agent/README.md`. Eval report: `wpilot-agent/evals/report.md` (10/10).
- `wpilot-ui/` — Next.js console: coordinator page `/`, demo console `/demo`,
  no-login volunteer page `/confirm/[messageId]`. Quickstart in `wpilot-ui/README.md`.
- `docs/` — `ARCHITECTURE.md` (diagram) · `SUBMISSION.md` (Devpost text) ·
  `VIDEO-SCRIPT.md` · `BUILDER-POST.md` (bonus-post draft) · `DEPLOY.md` (runbook).
- `Dockerfile.api` + `fly.toml` — demo API image (verified locally).

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
