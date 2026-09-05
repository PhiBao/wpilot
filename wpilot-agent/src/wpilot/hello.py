"""SDK smoke test: verifies the Strands tool loop runs locally.

Uses a deterministic in-process path (no model call) so `python -m wpilot.hello`
passes without AWS credentials. A live Bedrock-backed agent is wired in the
campaign module.
"""

from strands import Agent, tool


@tool
def roster_count() -> str:
    """Return how many volunteers are in the seeded demo roster."""
    import csv
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent.parent / "seeds" / "volunteers.csv"
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return f"Seeded roster has {len(rows)} volunteers"


def main() -> None:
    agent = Agent(tools=[roster_count])
    # Direct tool call exercises the tool registry without a model round-trip.
    result = agent.tool.roster_count()
    print(f"wpilot hello OK: {result}")


if __name__ == "__main__":
    main()
