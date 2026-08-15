"""Offline: turn collected trajectories into preference pairs and eval metrics.

Runs against Supabase, not inside Blender. Nothing here touches the MCP server
or the addon.

Two outputs:

1. Preference pairs — a step that was undone (rejected) against the step that
   replaced it (accepted). This is the signal published scene benchmarks cannot
   produce: they score a final scene, we observed the correction happen.

2. Reference-free metrics — undo rate, error taxonomy, retry depth,
   steps-to-completion. Proxies for agent quality that need no ground truth.

Usage:
    python scripts/mine_preferences.py --out preferences.jsonl
    python scripts/mine_preferences.py --metrics-only
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from typing import Any, Iterable

try:
    import httpx
except ImportError:
    sys.exit("pip install httpx")

PAGE_SIZE = 1000
# Steps within this many seconds before an undo are treated as its target.
UNDO_WINDOW_SECONDS = 120


def fetch_all(url: str, key: str, table: str, since: int | None = None) -> list[dict]:
    """Page through a Supabase table."""
    rows: list[dict] = []
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    offset = 0
    while True:
        params = {
            "select": "*",
            "order": "event_timestamp.asc",
            "limit": str(PAGE_SIZE),
            "offset": str(offset),
        }
        if since:
            params["event_timestamp"] = f"gte.{since}"
        response = httpx.get(
            f"{url}/rest/v1/{table}", headers=headers, params=params, timeout=60.0
        )
        response.raise_for_status()
        batch = response.json()
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def group_trajectories(steps: Iterable[dict]) -> dict[str, list[dict]]:
    """Bucket steps by trajectory, ordered by step_index."""
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for step in steps:
        tid = step.get("trajectory_id")
        if tid:
            grouped[tid].append(step)
    for group in grouped.values():
        group.sort(key=lambda s: s.get("step_index") or 0)
    return grouped


def _action_of(step: dict) -> dict:
    return step.get("action") or {}


def _is_mutation(step: dict) -> bool:
    """Skip OBSERVE steps: they change nothing, so they cannot be preferred."""
    return _action_of(step).get("semantic") not in (None, "OBSERVE", "UNKNOWN")


def build_preference_pairs(
    steps: list[dict], feedback: list[dict]
) -> list[dict[str, Any]]:
    """Pair each rejected step with the step that superseded it.

    Rejection comes from an undo feedback row (observed in Blender, not
    self-reported by the agent). The accepted side is the next mutating step in
    the same trajectory that was not itself undone.
    """
    by_trajectory = group_trajectories(steps)

    rejected: set[tuple[str, int]] = set()
    for row in feedback:
        if row.get("feedback") != "undo":
            continue
        tid, idx = row.get("trajectory_id"), row.get("step_index")
        if tid is not None and idx is not None:
            rejected.add((tid, idx))

    pairs: list[dict[str, Any]] = []
    for tid, group in by_trajectory.items():
        for position, step in enumerate(group):
            idx = step.get("step_index")
            if (tid, idx) not in rejected or not _is_mutation(step):
                continue

            replacement = None
            for candidate in group[position + 1 :]:
                if not _is_mutation(candidate):
                    continue
                if (tid, candidate.get("step_index")) in rejected:
                    continue  # also undone; keep looking
                replacement = candidate
                break
            if replacement is None:
                continue

            goal = step.get("goal_text")
            # Inherited goals are often not this step's real intent.
            if step.get("goal_source") != "call" or not goal:
                continue

            pairs.append({
                "trajectory_id": tid,
                "goal": goal,
                "rejected": {
                    "step_index": idx,
                    "semantic": _action_of(step).get("semantic"),
                    "tool_name": _action_of(step).get("tool_name"),
                    "raw_code": _action_of(step).get("raw_code"),
                    "state_delta": step.get("state_delta"),
                },
                "chosen": {
                    "step_index": replacement.get("step_index"),
                    "semantic": _action_of(replacement).get("semantic"),
                    "tool_name": _action_of(replacement).get("tool_name"),
                    "raw_code": _action_of(replacement).get("raw_code"),
                    "state_delta": replacement.get("state_delta"),
                },
            })
    return pairs


def compute_metrics(steps: list[dict], feedback: list[dict]) -> dict[str, Any]:
    """Reference-free quality proxies. No ground truth required."""
    by_trajectory = group_trajectories(steps)
    agent_steps = [s for s in steps if s.get("actor") == "agent"]

    undone = {
        (r.get("trajectory_id"), r.get("step_index"))
        for r in feedback
        if r.get("feedback") == "undo"
    }

    per_tool: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"calls": 0, "failures": 0, "undone": 0}
    )
    errors: collections.Counter = collections.Counter()

    for step in agent_steps:
        tool = _action_of(step).get("tool_name") or "unknown"
        stats = per_tool[tool]
        stats["calls"] += 1
        outcome = step.get("outcome") or {}
        if not outcome.get("success", True):
            stats["failures"] += 1
            message = (outcome.get("error") or "").strip().splitlines()
            if message:
                # Bucket by leading text; full messages carry unique names.
                errors[message[0][:80]] += 1
        if (step.get("trajectory_id"), step.get("step_index")) in undone:
            stats["undone"] += 1

    human_steps = sum(1 for s in steps if s.get("actor") == "human")
    lengths = [len(g) for g in by_trajectory.values()]

    def rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    total_failures = sum(t["failures"] for t in per_tool.values())

    return {
        "trajectories": len(by_trajectory),
        "steps_total": len(steps),
        "steps_agent": len(agent_steps),
        "steps_human": human_steps,
        "human_intervention_rate": rate(human_steps, len(steps)),
        "undo_rate": rate(len(undone), len(agent_steps)),
        "failure_rate": rate(total_failures, len(agent_steps)),
        "median_trajectory_length": (
            sorted(lengths)[len(lengths) // 2] if lengths else 0
        ),
        "per_tool": {
            tool: {
                **stats,
                "failure_rate": rate(stats["failures"], stats["calls"]),
                "undo_rate": rate(stats["undone"], stats["calls"]),
            }
            for tool, stats in sorted(
                per_tool.items(), key=lambda kv: -kv[1]["calls"]
            )
        },
        "top_errors": errors.most_common(15),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--key", default=os.environ.get("SUPABASE_KEY"))
    parser.add_argument("--out", help="write preference pairs as JSONL")
    parser.add_argument("--metrics-only", action="store_true")
    parser.add_argument("--since", type=int, help="unix timestamp lower bound")
    args = parser.parse_args()

    if not args.url or not args.key:
        return parser.error("set --url/--key or SUPABASE_URL/SUPABASE_KEY")

    steps = fetch_all(args.url, args.key, "trajectory_steps", args.since)
    feedback = fetch_all(args.url, args.key, "trajectory_feedback", args.since)
    print(f"fetched {len(steps)} steps, {len(feedback)} feedback rows", file=sys.stderr)

    metrics = compute_metrics(steps, feedback)
    print(json.dumps(metrics, indent=2))

    if args.metrics_only:
        return 0

    pairs = build_preference_pairs(steps, feedback)
    print(f"built {len(pairs)} preference pairs", file=sys.stderr)
    if args.out:
        with open(args.out, "w") as handle:
            for pair in pairs:
                handle.write(json.dumps(pair) + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
