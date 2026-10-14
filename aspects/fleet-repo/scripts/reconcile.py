###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Compute the rollout ChangeSet for the ``fleet-repo`` aspect (rules 1 and 2).

Standalone and stdlib-only (Python 3.11+); imports nothing from any engine. Both
rules are CHECK ONLY: the records are evidence, written once by the rollout engine,
and the index renderer belongs to the rollout engine. So the ChangeSet is always
empty, with a stable digest; ``check.py`` reports the findings.

Usage::

    python reconcile.py <repo> [<repo> ...]
    python reconcile.py --json <repo> [<repo> ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def _digest(changes: list[dict]) -> str:
    blob = json.dumps(changes, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def reconcile_repo(repo: Path) -> dict:  # noqa: ARG001 - check only: the repository is not read
    """The ChangeSet for one repository: always empty."""
    changes: list[dict] = []
    return {"applicable": True, "changeset": changes, "decisions_required": [], "digest": _digest(changes)}


def main(argv: list[str] | None = None) -> int:
    """Compute the ChangeSet for each repository and print it."""
    parser = argparse.ArgumentParser(description="Compute the fleet-repo rollout ChangeSet (always empty).")
    parser.add_argument("repos", nargs="+", type=Path, help="repository directories")
    parser.add_argument("--json", action="store_true", help="emit the ChangeSet as JSON")
    args = parser.parse_args(argv)
    results = {repo.resolve().name: reconcile_repo(repo) for repo in args.repos}
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    for name, r in results.items():
        print(f"\n{name}: {len(r['changeset'])} change(s) [{r['digest'][:12]}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
