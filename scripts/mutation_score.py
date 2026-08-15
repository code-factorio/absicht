"""Turn mutmut's CI/CD stats into a pass/fail mutation score.

`mutmut run` exits zero however many mutants survive, so the threshold has to
live somewhere. Here, reading the JSON mutmut writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def score(stats: dict[str, int]) -> float:
    """Killed mutants as a percentage of the mutants the tests actually ran.

    Mutants with no covering test (`no_tests`) and mutants that never finished
    (`timeout`, `suspicious`, `segfault`) are excluded: they say something about
    coverage or about mutmut, not about whether the tests can tell right from
    wrong.
    """
    killed = stats.get("killed", 0)
    survived = stats.get("survived", 0)
    judged = killed + survived
    if judged == 0:
        return 0.0
    return 100.0 * killed / judged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stats", type=Path, help="path to mutmut-cicd-stats.json")
    parser.add_argument(
        "--floor",
        type=float,
        required=True,
        help="minimum acceptable mutation score, as a percentage",
    )
    args = parser.parse_args()

    if not args.stats.exists():
        print(f"mutation: {args.stats} is missing; did `mutmut run` finish?", file=sys.stderr)
        return 2

    stats: dict[str, int] = json.loads(args.stats.read_text())
    percentage = score(stats)
    print(
        f"mutation: {percentage:.1f}% killed "
        f"({stats.get('killed', 0)} killed, {stats.get('survived', 0)} survived, "
        f"{stats.get('no_tests', 0)} uncovered, {stats.get('timeout', 0)} timed out)"
    )
    if percentage < args.floor:
        print(f"mutation: below the floor of {args.floor:.0f}%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
