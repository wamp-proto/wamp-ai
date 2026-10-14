###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Check repositories against the ``aspect-repo`` aspect (rule 1: the aspect folder contract).

Standalone and stdlib-only (Python 3.11+). For each repository: does every
``aspects/<name>/`` have valid SKILL.md frontmatter and ``aspect.toml``, ``requires``
that resolve, an interface that is present, standard library only, network-free and
deterministic, and no machine-local paths (see ``_ar.py``)?

Usage::

    python check.py <repo> [<repo> ...]
    python check.py --json <repo> [<repo> ...]

Exit status 1 if any repository FAILs. A repository with no aspect yet is a WARN.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from _ar import FAIL, OK, WARN, Finding, inspect

inspect_repo = inspect


def _worst(findings: list[Finding]) -> str:
    statuses = {f.status for f in findings}
    return FAIL if FAIL in statuses else WARN if WARN in statuses else OK


def main(argv: list[str] | None = None) -> int:
    """Run the checker over the given repositories and print a report."""
    parser = argparse.ArgumentParser(description="Check repositories against the aspect-repo aspect.")
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
