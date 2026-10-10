###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Shared logic of the ``way-a`` aspect: the desired tooling pins, and what a target has.

Standalone and stdlib-only (Python 3.11+); imports nothing from any engine.

THE DESIRED PINS COME FROM THIS CHECKOUT OF wamp-ai - the one this script runs from:

- desired wamp-ai  = this checkout's commit (the aspect's provider revision);
- desired wamp-cicd = the wamp-cicd commit this checkout's ``deps.toml`` pins.

So moving every repository to a new wamp-cicd is one reviewed change in wamp-ai (its
``deps.toml``) plus one rollout, and the answer is reproducible from the rollout record
(provider revision) with no network lookup. Run from a target's own pin of wamp-ai
(``just check-aspect``), the check therefore asks "is this repository consistent with
the wamp-ai it pins?"; run from a newer wamp-ai by the rollout tooling, the reconcile
moves the pins forward.

TWO LAYOUTS (TOOLING-STRUCTURE.md):

- **ordinary repository**: wamp-ai and wamp-cicd as submodules ``.ai`` and ``.cicd``;
- **pinned repository** (a tooling source, or an aspect repository): no submodules,
  both as ``deps.toml`` entries, checked out in ``.deps/``. wamp-ai carries no wamp-ai
  entry and wamp-cicd no wamp-cicd entry: a repository does not depend on itself.

A target is pinned when it has a ``deps.toml``, declares the ``aspect-repo`` aspect in
its ``aspects.toml``, or is wamp-cicd. Submodules in a pinned repository are a finding;
converting a layout is a deliberate change, not a pin move.
"""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

WAMP_AI = "wamp-ai"
WAMP_CICD = "wamp-cicd"
URLS = {
    WAMP_AI: "https://github.com/wamp-proto/wamp-ai.git",
    WAMP_CICD: "https://github.com/wamp-proto/wamp-cicd.git",
}
SUBMODULE = {WAMP_AI: ".ai", WAMP_CICD: ".cicd"}

PROVIDER = Path(__file__).resolve().parents[3]  # aspects/way-a/scripts/_wa.py -> wamp-ai


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def desired() -> dict[str, str]:
    """``{wamp-ai: commit, wamp-cicd: commit}`` from this checkout of wamp-ai."""
    ai = _git(PROVIDER, "rev-parse", "HEAD")
    deps = PROVIDER / "deps.toml"
    cicd = ""
    if deps.is_file():
        cicd = str((tomllib.loads(deps.read_text(encoding="utf-8")).get(WAMP_CICD) or {}).get("commit", ""))
    if not ai or not cicd:
        msg = f"cannot read the desired pins from {PROVIDER} (a git checkout of wamp-ai with deps.toml)"
        raise RuntimeError(msg)
    return {WAMP_AI: ai, WAMP_CICD: cicd}


def _aspects(target: Path) -> list[str]:
    toml = target / "aspects.toml"
    if not toml.is_file():
        return []
    return list(tomllib.loads(toml.read_text(encoding="utf-8")).get("aspects") or [])


def is_self(target: Path) -> bool:
    """The target is this very checkout of wamp-ai (self-hosting)."""
    return target.resolve() == PROVIDER


def is_pinned(target: Path) -> bool:
    """A pinned repository: tooling in deps.toml/.deps, no submodules."""
    return (
        (target / "deps.toml").is_file()
        or "aspect-repo" in _aspects(target)
        or target.resolve().name == WAMP_CICD
        or is_self(target)
    )


def gitlinks(target: Path) -> dict[str, str]:
    """Submodule path -> pinned commit, from the target's INDEX.

    The index, like deps.toml in the working tree: a staged pin move counts. In a clean
    tree the index is HEAD.
    """
    out: dict[str, str] = {}
    for line in _git(target, "ls-files", "--stage").splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[0] == "160000":
            out[path] = parts[1]
    return out


def deps_pins(target: Path) -> dict[str, dict]:
    """deps.toml entries of the target (empty without the file)."""
    deps = target / "deps.toml"
    if not deps.is_file():
        return {}
    return dict(tomllib.loads(deps.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class PinState:
    """One tooling dependency: what the target has, and what it should have."""

    name: str  # wamp-ai / wamp-cicd
    layout: str  # "submodule" / "deps"
    have: str  # commit the target pins, "" if absent
    want: str  # desired commit
    have_url: str  # url the target records, "" if absent

    @property
    def ok(self) -> bool:
        return self.have == self.want and self.have_url == URLS[self.name]


def pin_states(target: Path) -> tuple[list[PinState], list[str]]:
    """The tooling pins this target must have, and layout problems found on the way."""
    want = desired()
    problems: list[str] = []
    states: list[PinState] = []
    links = gitlinks(target)
    if is_pinned(target):
        stray = [p for p in (SUBMODULE[WAMP_AI], SUBMODULE[WAMP_CICD]) if p in links]
        if stray:
            problems.append(
                f"submodule(s) {', '.join(stray)} in a pinned repository - convert to deps.toml/.deps "
                f"(a layout change, made deliberately, not by a pin move)"
            )
        deps = deps_pins(target)
        own = target.resolve().name
        for name in (WAMP_AI, WAMP_CICD):
            if is_self(target) or own == name:
                continue  # a repository does not depend on itself
            entry = deps.get(name) or {}
            states.append(
                PinState(name, "deps", str(entry.get("commit", "")), want[name], str(entry.get("url", "")))
            )
    else:
        urls = submodule_urls(target)
        for name in (WAMP_AI, WAMP_CICD):
            path = SUBMODULE[name]
            states.append(PinState(name, "submodule", links.get(path, ""), want[name], urls.get(path, "")))
    return states, problems


def submodule_urls(target: Path) -> dict[str, str]:
    """Submodule path -> url, from the target's .gitmodules."""
    gm = target / ".gitmodules"
    if not gm.is_file():
        return {}
    out = _git(target, "config", "-f", ".gitmodules", "--get-regexp", r"^submodule\..*\.(path|url)$")
    paths: dict[str, str] = {}
    urls: dict[str, str] = {}
    for line in out.splitlines():
        key, _, value = line.partition(" ")
        name = key[len("submodule.") : key.rfind(".")]
        (paths if key.endswith(".path") else urls)[name] = value
    return {paths[n]: urls.get(n, "") for n in paths}
