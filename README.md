# wpilot

The backfill agent for volunteer-run shifts. When a shift goes short, wpilot works
the phone tree — texts the right volunteers, locks in a commitment, updates the
roster — and only interrupts the coordinator when a human actually needs to decide.

Built for the **Agents for Humans** hackathon (Good Neighbor track) with the
[Strands Agents SDK](https://strandsagents.com/).

## Layout

- `wpilot-agent/` — Python agent service (Strands): campaign loop, tools, policy,
  messaging, receipts, evals. See `wpilot-agent/README.md`.
- `wpilot-ui/` — Next.js coordinator console + volunteer confirm page + demo
  console (scaffold lands Sep 9 per build plan).

## Quickstart (agent)

```bash
cd wpilot-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m wpilot.hello
```

## Status

Day 5 scaffold. See build plan in project thread. License: MIT.
