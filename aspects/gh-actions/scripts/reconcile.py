###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Compute the rollout ChangeSet for the ``gh-actions`` aspect.

Standalone and stdlib-only (Python 3.11+), offline; imports nothing from any engine. It
reads a repository and **emits a ChangeSet as JSON**; it changes nothing. One op per
``uses:`` line that is not pinned as the table (or a current deviation decision) says:

- ``line_replace {path, line, old, new}``: the whole line, without its ending, before
  and after. ``new`` keeps the line's indentation and ``- ``, drops quotes around the
  value, and ends in ``@<sha> # <version>``. No other byte of the file changes.

No op for what a human must look at: an action not in the pin table, a malformed or
``docker://`` value, a workflow in a subdirectory, a broken or stale decision. Those
are the check's findings. While a ``.decisions/gh-actions/OPEN-*.toml`` exists, the
ChangeSet is empty, and the check fails on it (rule 3).

``decisions_required`` is always ``[]``: gh-actions asks no questions. A bump is decided
in the pin table, and a member that stays behind writes its ``gh_actions_deviation``
decision itself. (The fleet manager reads that key as question records and writes an
``OPEN-*.toml`` for each, wamp-proto/wamp-ai#46.)

Output is canonical and deterministic (ops sorted by path and line, no timestamps), so
the same inputs give the same JSON and ``digest``.

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

from _gha import action_key, kept, load_table, open_decision_files, pinned_line, scan, workflow_files


def _digest(changes: list[dict]) -> str:
    blob = json.dumps(changes, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def reconcile_repo(repo: Path) -> dict:
    """The ChangeSet for one repository."""
    files, _dead = workflow_files(repo)
    pending = open_decision_files(repo)
    changes: list[dict] = []
    if files and not pending:
        table = load_table()
        keep, _problems = kept(repo, table)
        for use in scan(repo):
            if use.kind != "third-party":
                continue
            key = action_key(use.name)
            pin = keep.get(key) or table.get(key)
            if pin is None:
                continue
            new = pinned_line(use.lead, use.name, pin)
            if use.text != new:
                changes.append(
                    {"action": "line_replace", "kind": "file_modify", "path": use.path,
                     "line": use.line, "old": use.text, "new": new}
                )
    changes.sort(key=lambda c: (c["path"], c["line"]))
    return {
        "applicable": bool(files),
        "changeset": changes,
        "decisions_required": [],
        "digest": _digest(changes),
    }


def main(argv: list[str] | None = None) -> int:
    """Compute the ChangeSet for each repository and print it."""
    parser = argparse.ArgumentParser(description="Compute the gh-actions rollout ChangeSet.")
    parser.add_argument("repos", nargs="+", type=Path, help="repository directories")
    parser.add_argument("--json", action="store_true", help="emit the ChangeSet as JSON")
    args = parser.parse_args(argv)
    results = {repo.resolve().name: reconcile_repo(repo) for repo in args.repos}
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0
    for name, r in results.items():
        print(f"\n{name}: {len(r['changeset'])} change(s) [{r['digest'][:12]}]")
        for c in r["changeset"]:
            print(f"  {c['path']}:{c['line']}: {c['new'].strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
