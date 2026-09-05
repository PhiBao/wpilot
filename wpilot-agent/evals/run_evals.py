"""Eval runner: executes all scenarios, writes evals/report.md, exits nonzero on failure."""

from __future__ import annotations

from datetime import datetime, timezone

from .scenarios import SCENARIOS

REPORT = __file__.replace("run_evals.py", "report.md")


def main() -> int:
    rows: list[tuple[str, str, str, str]] = []
    failed = 0
    for s in SCENARIOS:
        try:
            detail = s.run()
            rows.append((s.name, "PASS", s.guarantee, detail))
        except AssertionError as e:
            failed += 1
            rows.append((s.name, "FAIL", s.guarantee, f"assertion: {e}"))
        except Exception as e:  # noqa: BLE001 — evals must report, not crash
            failed += 1
            rows.append((s.name, "ERROR", s.guarantee, f"{type(e).__name__}: {e}"))

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# wpilot eval report",
        "",
        f"Ran {len(rows)} scenarios · {len(rows) - failed} passed · {failed} failed · {stamp}",
        "",
        "Method: real engine + policy + store, scripted/silent simulated channel,",
        "zero sleeps. Each scenario asserts a product guarantee a coordinator",
        "or judge would care about — not an implementation detail.",
        "",
        "| Scenario | Result | Guarantee | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for name, result, guarantee, detail in rows:
        lines.append(f"| {name} | {result} | {guarantee} | {detail} |")
    lines += [
        "",
        "Reproduce: `cd wpilot-agent && source .venv/bin/activate && python -m evals.run_evals`",
        "",
    ]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"{len(rows) - failed}/{len(rows)} scenarios passed -> {REPORT}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
