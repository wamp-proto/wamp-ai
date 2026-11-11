###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Report which entries of the gh-actions pin table are behind the newest releases.

NOT part of the aspect's interface: ``check.py`` and ``reconcile.py`` stay offline and
deterministic; this script asks the network. It runs weekly in wamp-ai's own CI
(``.github/workflows/gh-actions-latest.yml``) and by hand before a table bump.

For each table entry it lists the action's version tags with ``git ls-remote --tags``
(no API token, no rate limit), keeps the ``vMAJOR.MINOR.PATCH`` ones (a pre-release or
a tag of another shape, such as codeql-action's ``codeql-bundle-*``, is not a release of
the action) and reports the newest release in the pinned major and the newest overall,
each with the commit it points to, so a table bump can be copied from the output.

Usage::

    python latest.py               # a Markdown report
    python latest.py --json
    python latest.py --exit-code   # exit 2 if any entry is behind

Exit status 1 if a tag list cannot be read.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass

from _gha import Pin, load_table

RELEASE_TAG = re.compile(r"^refs/tags/(v(\d+)\.(\d+)\.(\d+))(\^\{\})?$")


def ls_remote(action: str) -> str:
    """``git ls-remote --tags`` of the action's GitHub repository."""
    proc = subprocess.run(
        ["git", "ls-remote", "--tags", f"https://github.com/{action}.git"],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if proc.returncode != 0:
        msg = f"{action}: git ls-remote failed: {proc.stderr.strip()}"
        raise RuntimeError(msg)
    return proc.stdout


def releases(listing: str) -> dict[tuple[int, int, int], Pin]:
    """``{(major, minor, patch): Pin}`` from an ls-remote listing; an annotated tag's
    peeled commit (``^{}``) wins over the tag object."""
    out: dict[tuple[int, int, int], Pin] = {}
    for line in listing.splitlines():
        sha, _, ref = line.partition("\t")
        m = RELEASE_TAG.match(ref.strip())
        if not m:
            continue
        key = (int(m[2]), int(m[3]), int(m[4]))
        if m[5] or key not in out:
            out[key] = Pin(sha.strip(), m[1])
    return out


@dataclass(frozen=True)
class Row:
    action: str
    pinned: str
    in_major: str  # newest release in the pinned major
    in_major_sha: str
    newest: str
    newest_sha: str
    status: str  # current / minor behind / major behind / pin not a release

    @property
    def behind(self) -> bool:
        return self.status != "current"


def compare(action: str, pin: Pin, listing: str) -> Row:
    """One table entry against the action's releases."""
    rel = releases(listing)
    key = tuple(int(x) for x in pin.version[1:].split("."))
    if not rel or key not in rel or rel[key].sha != pin.sha:
        status = "pin not a release"
    else:
        status = "current"
    newest = rel[max(rel)] if rel else pin
    same_major = [k for k in rel if k[0] == pin.major]
    in_major = rel[max(same_major)] if same_major else pin
    if status == "current":
        if newest.major > pin.major:
            status = "major behind"
        elif in_major.version != pin.version:
            status = "minor behind"
    return Row(action, pin.version, in_major.version, in_major.sha, newest.version, newest.sha, status)


def report(lister: Callable[[str], str] = ls_remote) -> list[Row]:
    """A row per table entry, in table order."""
    return [compare(action, pin, lister(action)) for action, pin in load_table().items()]


def markdown(rows: list[Row]) -> str:
    behind = [r for r in rows if r.behind]
    lines = [
        "# gh-actions: pin table vs newest releases",
        "",
        f"{len(behind)} of {len(rows)} entries behind." if behind else f"All {len(rows)} entries current.",
        "",
        "| action | pinned | newest in major | newest | status |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| `{r.action}` | {r.pinned} | {r.in_major} | {r.newest} | {r.status} |")
    if behind:
        lines += ["", "Table entries for the newest releases (`references/actions.toml`):", "", "```toml"]
        for r in behind:
            lines += [f'[action."{r.action}"]', f'sha     = "{r.newest_sha}"', f'version = "{r.newest}"', ""]
        lines[-1] = "```"
        lines += ["", "A new major is a decision for every member: check its release notes before the bump."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Print the report."""
    parser = argparse.ArgumentParser(description="Report pin-table entries behind the newest releases.")
    parser.add_argument("--json", action="store_true", help="emit the rows as JSON")
    parser.add_argument("--exit-code", action="store_true", help="exit 2 if any entry is behind")
    args = parser.parse_args(argv)
    try:
        rows = report()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps([asdict(r) | {"behind": r.behind} for r in rows], indent=2, sort_keys=True))
    else:
        print(markdown(rows), end="")
    return 2 if args.exit_code and any(r.behind for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
