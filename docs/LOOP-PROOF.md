# Loop proof: real Strands agent, real tools, real interrupt, cross-process resume

Model: `mistral.ministral-3-8b-instruct` via the Bedrock **mantle**
OpenAI-compatible endpoint (bearer auth) — the only inference path this
AWS account's verification status leaves open. Guided steps (small models
need step-by-step prompts; the loop, tools, interrupts, and session resume
are identical on any provider). Reproduce:
`WPILOT_PROOF_MODEL=mantle:mistral.ministral-3-8b-instruct python evals/loop_proof_ollama.py A`,
then `... B` in a NEW process (script header has the full commands).

## What happened (ground truth = receipts, not narration)

Phase A (process 1, exits at the end):
- `offer_sent` Casey (V8) → `offer_reply` NO; Devon (V2) → NO; Alex (V6) → **YES**
- `book_slot(V6)` → **stop_reason=interrupt**, `wpilot-booking-approval`:
  Alex, reliability 0.43 < 0.50, coordinator must confirm.

Phase B (new process, same `session_dir`):
- Answers the interrupt with trust (`t`); session resumes mid-loop
- Consent re-verified against the durable offers table (not memory)
- `slot_filled`: V6 (Alex) accepted. **S1 6/6 filled, round 1, no nudges.**

## What this proves

1. The agent loop drives real tools with real args over a hosted model.
2. The approval hook pauses `book_slot` with a structured, actionable reason.
3. Session-managed interrupts survive process death.
4. **Consent is durable**: `book_slot` verifies a recorded YES in the
   offers/replies tables — a fresh process with an empty in-memory channel
   still honors (and still enforces) prior consent. Regression-tested
   (`test_consent_survives_channel_replacement`).
5. Audit taxonomy is enforced (`log_receipt` allowlists escalation/note/deferral).

## Found and fixed during this proof (all in repo + tests)

- Model booked a volunteer who said NO → consent verification added.
- Model invented receipt kinds → kind allowlist added.
- `send_offer`/`book_slot` raised raw tracebacks on bad IDs → actionable
  FAILED strings.
- pytest was ambient-credential-dependent → hermetic `conftest.py`.
- Live public run exposed `rank_candidates` tool recursing into itself
  (name shadowed the policy import) → aliased import + regression test.

## Honest limitations

- Guided steps compensate for small-model planning; ranking, eligibility,
  and safety are deterministic code either way.
- Small-model narration drifts from reality; receipts are the ground truth
  (the demo UI shows receipts, not narration, for the same reason).
