###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Check repositories against the ``way-a`` aspect (rule 1: the tooling pins).

Standalone and stdlib-only (Python 3.11+). For each repository: is wamp-ai and
wamp-cicd pinned where its layout says (submodules ``.ai``/``.cicd``, or ``deps.toml``
entries), at the commits the wamp-ai checkout this runs from desires (see ``_wa.py``)?

Usage::

    python check.py <repo> [<repo> ...]
    python check.py --json <repo> [<repo> ...]

Exit status 1 if any repository FAILs.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from _wa import URLS, is_self, pin_states

OK, WARN, FAIL = "OK", "WARN", "FAIL"


@dataclass(frozen=True)
class Finding:
    rule: str
    status: str
    message: str


def inspect_repo(repo: Path) -> list[Finding]:
    """The ``way-a`` findings for one repository."""
    if is_self(repo):
        return [Finding("tooling-pins", OK, "wamp-ai itself: its deps.toml is the source of the desired pins")]
    states, problems = pin_states(repo)
    out = [Finding("layout", FAIL, p) for p in problems]
    for s in states:
        where = f".deps ({s.name} in deps.toml)" if s.layout == "deps" else s.name
        if not s.have:
            out.append(Finding("tooling-pins", FAIL, f"{where}: not pinned - want {s.want[:7]}"))
        elif s.have != s.want:
            out.append(Finding("tooling-pins", FAIL, f"{where}: at {s.have[:7]}, want {s.want[:7]}"))
        elif s.have_url != URLS[s.name]:
            out.append(Finding("tooling-pins", FAIL, f"{where}: url {s.have_url!r}, want {URLS[s.name]!r}"))
        else:
            out.append(Finding("tooling-pins", OK, f"{where}: at {s.have[:7]}"))
    return out


def _worst(findings: list[Finding]) -> str:
    statuses = {f.status for f in findings}
    return FAIL if FAIL in statuses else WARN if WARN in statuses else OK


def main(argv: list[str] | None = None) -> int:
    """Run the checker over the given repositories and print a report."""
    parser = argparse.ArgumentParser(description="Check repositories against the way-a aspect.")
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
