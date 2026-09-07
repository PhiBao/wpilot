# wpilot eval report

Ran 15 scenarios · 15 passed · 0 failed · 2026-09-07 21:45 UTC

Method: real engine + policy + store, scripted/silent simulated channel,
zero sleeps. Each scenario asserts a product guarantee a coordinator
or judge would care about — not an implementation detail.

| Scenario | Result | Guarantee | Evidence |
| --- | --- | --- | --- |
|  | PASS |  | FILLED by V1 after asking 1 |
|  | PASS |  | V1 declined -> V8 booked |
|  | PASS |  | asked 1, booked 0, receipts explain why |
|  | PASS |  | asked only ['V3'] |
|  | PASS |  | V7 scripted YES but never asked |
|  | PASS |  | 0 messages sent at 22:30 |
|  | PASS |  | V1 skipped after 2 prior asks; V8 booked |
|  | PASS |  | full shift untouched |
|  | PASS |  | booked V6 with review flag |
|  | PASS |  | 15 receipts, ending in pool_exhausted |
| traj-routine-fill | PASS | Trajectory matches a safe run shape. | offer_sent -> offer_reply -> slot_filled |
| traj-cascade | PASS | Trajectory matches a safe run shape. | offer_sent -> offer_reply -> offer_sent -> offer_reply -> slot_filled |
| traj-silence | PASS | Trajectory matches a safe run shape. | offer_sent -> offer_timeout -> pool_exhausted |
| traj-quiet | PASS | Trajectory matches a safe run shape. | deferred_quiet_hours |
| traj-full-shift | PASS | Trajectory matches a safe run shape. | no_gap |

Reproduce: `cd wpilot-agent && source .venv/bin/activate && python -m evals.run_evals`
