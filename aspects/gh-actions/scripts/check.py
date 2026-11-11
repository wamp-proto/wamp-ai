###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Check repositories against the ``gh-actions`` aspect: every third-party ``uses:`` is
pinned to the commit the pin table says, with its version as a comment.

Standalone and stdlib-only (Python 3.11+), offline. See ``_gha.py`` for what is read
and what is pinned.

Usage::

    python check.py <repo> [<repo> ...]
    python check.py --json <repo> [<repo> ...]

Exit status 1 if any repository FAILs.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from _gha import TableError, action_key, kept, load_table, open_decision_files, pinned_line, scan, workflow_files

OK, WARN, FAIL = "OK", "WARN", "FAIL"


@dataclass(frozen=True)
class Finding:
    rule: str
    status: str
    message: str


def inspect_repo(repo: Path) -> list[Finding]:
    """The ``gh-actions`` findings for one repository."""
    try:
        table = load_table()
    except TableError as exc:
        return [Finding("pin-table", FAIL, str(exc))]
    out: list[Finding] = []

    for path in open_decision_files(repo):
        out.append(Finding("open-decisions", FAIL, f"{path}: a decision asked for and not yet taken"))

    keep, problems = kept(repo, table)
    out += [Finding("decisions", FAIL, p) for p in problems]

    files, dead = workflow_files(repo)
    for p in dead:
        rel = p.relative_to(repo).as_posix()
        why = "in a subdirectory of .github/workflows/, which GitHub does not run - not checked"
        out.append(Finding("dead-files", WARN, f"{rel}: {why}"))
    if not files:
        out.append(Finding("pins", OK, "no workflows"))
        return out

    pinned: Counter[str] = Counter()
    skipped = 0
    for use in scan(repo):
        where = f"{use.path}:{use.line}"
        kind = use.kind
        if kind in ("local", "first-party"):
            skipped += 1
            continue
        if kind == "docker":
            out.append(Finding("pins", WARN, f"{where}: {use.value} - docker images are out of scope"))
            continue
        if kind == "malformed":
            out.append(Finding("pins", FAIL, f"{where}: {use.value!r} is not <owner>/<repo>[/<path>]@<ref>"))
            continue
        key = action_key(use.name)
        pin = keep.get(key) or table.get(key)
        if pin is None:
            out.append(Finding("pins", FAIL, f"{where}: {key} is not in the pin table"))
            continue
        if use.text == pinned_line(use.lead, use.name, pin):
            pinned[use.path] += 1
            continue
        how = "kept by a deviation decision at" if key in keep else "want"
        have = use.ref if not use.comment else f"{use.ref} # {use.comment}"
        out.append(Finding("pins", FAIL, f"{where}: {use.name}@{have} - {how} {pin.sha[:7]} # {pin.version}"))

    for path in sorted(pinned):
        out.append(Finding("pins", OK, f"{path}: {pinned[path]} pinned"))
    if skipped:
        out.append(Finding("pins", OK, f"{skipped} local or first-party ref(s), not pinned by this aspect"))
    for action in sorted(keep):
        out.append(Finding("decisions", OK, f"{action} kept at {keep[action].version} by a deviation decision"))
    return out


def _worst(findings: list[Finding]) -> str:
    statuses = {f.status for f in findings}
    return FAIL if FAIL in statuses else WARN if WARN in statuses else OK


def main(argv: list[str] | None = None) -> int:
    """Run the checker over the given repositories and print a report."""
    parser = argparse.ArgumentParser(description="Check repositories against the gh-actions aspect.")
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
