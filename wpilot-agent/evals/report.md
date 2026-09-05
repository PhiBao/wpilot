# wpilot eval report

Ran 10 scenarios · 10 passed · 0 failed · 2026-09-05 08:05 UTC

Method: real engine + policy + store, scripted/silent simulated channel,
zero sleeps. Each scenario asserts a product guarantee a coordinator
or judge would care about — not an implementation detail.

| Scenario | Result | Guarantee | Evidence |
| --- | --- | --- | --- |
| routine-fill-zero-touches | PASS |  | FILLED by V1 after asking 1 |
| decline-cascades | PASS |  | V1 declined -> V8 booked |
| silence-escalates-cleanly | PASS |  | asked 1, booked 0, receipts explain why |
| only-eligible-texted | PASS |  | asked only ['V3'] |
| minor-never-contacted | PASS |  | V7 scripted YES but never asked |
| quiet-hours-defer | PASS |  | 0 messages sent at 22:30 |
| ask-cap-respected | PASS |  | V1 skipped after 2 prior asks; V8 booked |
| no-double-book | PASS |  | full shift untouched |
| low-reliability-flags-review | PASS |  | booked V6 with review flag |
| audit-completeness | PASS |  | 15 receipts, ending in pool_exhausted |

Reproduce: `cd wpilot-agent && source .venv/bin/activate && python -m evals.run_evals`
