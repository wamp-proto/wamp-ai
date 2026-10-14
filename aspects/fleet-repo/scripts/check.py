###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Check repositories against the ``fleet-repo`` aspect (rules 1 and 2: the rollout records and their index).

Standalone and stdlib-only (Python 3.11+). For each fleet repository: is every
``rollouts/<id>/rollout.toml`` well formed, and does it carry what its status promises
(rule 1)? Is ``rollouts/README.md`` consistent with the records (rule 2)? See ``_fr.py``.

Usage::

    python check.py <repo> [<repo> ...]
    python check.py --json <repo> [<repo> ...]

Exit status 1 if any repository FAILs. A fleet repository with no rollout yet is a WARN.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from _fr import FAIL, OK, WARN, Finding, inspect

inspect_repo = inspect


def _worst(findings: list[Finding]) -> str:
    statuses = {f.status for f in findings}
    return FAIL if FAIL in statuses else WARN if WARN in statuses else OK


def main(argv: list[str] | None = None) -> int:
    """Run the checker over the given repositories and print a report."""
    parser = argparse.ArgumentParser(description="Check repositories against the fleet-repo aspect.")
    parser.add_argument("repos", nargs="+", type=Path, help="repository directories to check")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)
    results = {repo.resolve().name: inspect_repo(repo) for repo in args.repos}
    if args.json:
        payload = {
            name: {"verdict": _worst(fs), "findings": [asdict(f) for f in fs]} for name, fs in results.items()
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for name, fs in results.items():
            print(f"\n{name}: {_worst(fs)}")
            for f in fs:
                print(f"  [{f.status:4}] {f.rule}: {f.message}")
    return 1 if any(_worst(fs) == FAIL for fs in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
