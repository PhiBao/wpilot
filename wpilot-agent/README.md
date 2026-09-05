# wpilot-agent

Python service for the wpilot backfill agent (Strands Agents SDK).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Pinned: `strands-agents==1.54.0`, `bedrock-agentcore==1.22.0` (see `pyproject.toml`).

## Verify

```bash
python -m wpilot.hello
```

Runs a local Strands agent with no model call (verifies SDK import + tool loop).
A live Bedrock-backed run needs AWS credentials and is wired up in the campaign
module (lands with the campaign engine).

## Layout (growing per build plan)

- `src/wpilot/hello.py` — SDK smoke test
- `src/wpilot/models.py` — shift / volunteer / campaign dataclasses (next)
- `src/wpilot/store.py` — CSV import + SQLite roster store (next)
- `src/wpilot/policy.py` — eligibility rules, Cedar-backed (next)
- `seeds/` — demo org CSVs (Harbor Pantry)
