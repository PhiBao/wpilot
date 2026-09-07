# Loop proof: real Strands agent, real tools, real interrupt, cross-process resume

Environment: local 8B open model (qwen3:8b / llama3.1:8b via Ollama) — no
frontier API needed. Guided steps (an 8B model needs step-by-step prompts;
the loop, tools, interrupts, and session resume are identical on any
provider). Reproduce: `python evals/loop_proof_ollama.py A`, then `... B`
in a NEW process (see script header).

## What happened (ground truth = receipts, not narration)

Phase A (process 1, PID exits at the end):
- `offer_sent` Maya (V1), Casey (V8), Devon (V2); `offer_reply` Devon → NO
- `offer_sent` Alex (V6)
- `book_slot(V6)` → **stop_reason=interrupt**
  `wpilot-booking-approval`: Alex, reliability 0.43 < 0.50, coordinator
  must confirm. Process exits. Nothing survives in memory.

Phase B (new process, same `session_dir`):
- Answers the interrupt with trust (`t`)
- Session resumes mid-loop; Alex's recorded YES verifies consent
- `slot_filled`: V6 (Alex) accepted. **S1 6/6 filled.**

## What this proves

1. The agent loop drives real tools with real args (not a script).
2. The approval hook pauses `book_slot` for sensitive bookings with a
   structured reason the coordinator can act on.
3. Session-managed interrupts survive process death — resume works from a
   cold process via the session store + persisted trust.
4. Consent verification blocks booking decliners: during this work an early
   run showed the model booking a volunteer who said NO; `book_slot` now
   REFUSEs without a recorded YES (tested: `test_book_slot_requires_recorded_yes`,
   `test_book_slot_refuses_decliner_even_if_asked`).
5. Audit taxonomy is enforced: the model once invented receipt kinds, so
   `log_receipt` now allowlists escalation/note/deferral.

## Honest limitations

- 8B narration drifts (it sometimes misreports what just happened). State
  changes are always receipted; receipts are the ground truth, in the demo
  UI as well as here.
- Guided steps compensate for 8B planning weakness. Ranking, eligibility,
  and safety decisions are deterministic code either way — the model never
  decides who is allowed, only the order it works an allowed list.
