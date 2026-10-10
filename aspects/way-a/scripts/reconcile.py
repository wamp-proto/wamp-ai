###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Compute the rollout ChangeSet for the ``way-a`` aspect (rule 1: the tooling pins).

Standalone and stdlib-only (Python 3.11+); imports nothing from any engine. It reads a
repository and **emits a ChangeSet as JSON**; it changes nothing. The ops are the
rollout tooling's two tooling-pin ops:

- ``submodule_pin {path, url, rev}`` for an ordinary repository (``.ai``, ``.cicd``);
- ``deps_pin {path: deps.toml, name, url, commit}`` for a pinned repository.

A pin is moved to exactly the desired commit (``_wa.py``): way-a owns these pins. A
layout problem (submodules in a pinned repository) yields no op - converting a layout
is a deliberate change. Output is canonical and deterministic (ops sorted, no
timestamps), so the same inputs give the same JSON and ``digest``.

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

from _wa import SUBMODULE, URLS, is_self, pin_states


def _digest(changes: list[dict]) -> str:
    blob = json.dumps(changes, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def reconcile_repo(repo: Path) -> dict:
    """The ChangeSet for one repository."""
    changes: list[dict] = []
    if not is_self(repo):
        states, _problems = pin_states(repo)
        for s in states:
            if s.ok:
                continue
            if s.layout == "submodule":
                changes.append(
                    {"action": "submodule_pin", "kind": "submodule_update", "path": SUBMODULE[s.name],
                     "url": URLS[s.name], "rev": s.want}
                )
            else:
                changes.append(
                    {"action": "deps_pin", "kind": "file_modify", "path": "deps.toml", "name": s.name,
                     "url": URLS[s.name], "commit": s.want}
                )
    changes.sort(key=lambda c: (c["path"], c.get("name", ""), c["action"]))
    return {"applicable": True, "changeset": changes, "decisions_required": [], "digest": _digest(changes)}


def main(argv: list[str] | None = None) -> int:
    """Compute the ChangeSet for each repository and print it."""
    parser = argparse.ArgumentParser(description="Compute the way-a rollout ChangeSet.")
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
            what = c.get("name") or c["path"]
            print(f"  {c['action']}: {what} -> {(c.get('rev') or c.get('commit'))[:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
