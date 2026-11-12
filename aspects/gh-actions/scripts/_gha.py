###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Shared logic of the ``gh-actions`` aspect: the pin table, and the ``uses:`` lines a
target has.

Standalone and stdlib-only (Python 3.11+); imports nothing from any engine and reads
nothing from the network.

THE DESIRED PINS COME FROM THIS CHECKOUT OF wamp-ai - the one this script runs from:
its ``references/actions.toml``. Run from a target's own pin of wamp-ai (``just
check-aspect``), the check asks "are this repository's workflows pinned as the wamp-ai
it pins says?"; run from a newer wamp-ai by the rollout tooling, the reconcile moves
the ``uses:`` lines forward.

WHAT IS READ: ``.github/workflows/*.yml`` / ``*.yaml`` (GitHub runs only these, not
files in subdirectories) and ``.github/actions/*/action.yml`` / ``action.yaml`` (local
composite actions). Line by line, without a YAML parser: a ``uses:`` key at the start of
a line, optionally after ``- ``. A reconcile then rewrites exactly that line and no other
byte of the file.

WHAT IS PINNED: every ``uses: <owner>/<repo>[/<path>]@<ref>``, except

- local actions (``./...``) and first-party refs (``wamp-proto/wamp-cicd/...``), which are
  called ``@main`` on purpose and pinned by wamp-cicd itself: skipped;
- ``docker://`` images: reported as out of scope.

A pinned line reads ``<owner>/<repo>[/<path>]@<sha> # <version>``, from the table entry
of ``<owner>/<repo>``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import tomllib

ASPECT = "gh-actions"
DEVIATION = "gh_actions_deviation"
DEVIATION_OPTIONS = ("keep", "follow")

TABLE = Path(__file__).resolve().parents[1] / "references" / "actions.toml"

FIRST_PARTY = ("wamp-proto/wamp-cicd/",)

SHA = re.compile(r"[0-9a-f]{40}")
VERSION = re.compile(r"v\d+\.\d+\.\d+")

# A `uses:` key at the start of a line (after indentation and an optional "- "), its
# value (optionally quoted), and whatever follows (spaces and a comment, or nothing).
USES = re.compile(
    r"^(?P<lead>[ \t]*(?:-[ \t]+)?uses:[ \t]*)"
    r"(?P<quote>[\"']?)(?P<value>[^\s\"'#]+)(?P=quote)"
    r"(?P<rest>[ \t]*(?:#.*)?)$"
)


@dataclass(frozen=True)
class Pin:
    """One table entry."""

    sha: str
    version: str

    @property
    def major(self) -> int:
        return int(self.version[1:].split(".")[0])


class TableError(ValueError):
    """The pin table is malformed - never silently half-read."""


def load_table(path: Path = TABLE) -> dict[str, Pin]:
    """``{owner/repo: Pin}`` from the pin table; raises :class:`TableError`."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        msg = f"{path.name}: cannot read the pin table: {exc}"
        raise TableError(msg) from exc
    actions = data.get("action")
    if not isinstance(actions, dict) or not actions:
        msg = f"{path.name}: no [action.\"<owner>/<repo>\"] entries"
        raise TableError(msg)
    table: dict[str, Pin] = {}
    problems = []
    for name, entry in sorted(actions.items()):
        if name.count("/") != 1 or not all(name.split("/")):
            problems.append(f"{name!r}: not <owner>/<repo>")
            continue
        sha = entry.get("sha") if isinstance(entry, dict) else None
        version = entry.get("version") if isinstance(entry, dict) else None
        if not (isinstance(sha, str) and SHA.fullmatch(sha)):
            problems.append(f"{name}: sha {sha!r} is not a full 40-hex commit")
        if not (isinstance(version, str) and VERSION.fullmatch(version)):
            problems.append(f"{name}: version {version!r} is not vMAJOR.MINOR.PATCH")
        if not problems:
            table[name] = Pin(sha, version)
    if problems:
        msg = f"{path.name}: " + "; ".join(problems)
        raise TableError(msg)
    return table


def action_key(name: str) -> str:
    """``owner/repo`` of ``owner/repo[/path]``."""
    return "/".join(name.split("/")[:2])


def pinned_line(lead: str, name: str, pin: Pin) -> str:
    """The line a pinned ``uses:`` must be."""
    return f"{lead}{name}@{pin.sha} # {pin.version}"


# --- what the target has ----------------------------------------------------------------


@dataclass(frozen=True)
class Use:
    """One ``uses:`` line of a target."""

    path: str  # repo-relative, posix
    line: int  # 1-based
    text: str  # the whole line, without its ending
    lead: str  # everything up to the value
    quote: str  # "" or the quote character around the value
    value: str  # owner/repo[/path]@ref, ./path, docker://...
    rest: str  # after the value: spaces and a comment, or ""

    @property
    def kind(self) -> str:
        """``local``, ``first-party``, ``docker``, ``malformed`` or ``third-party``."""
        if self.value.startswith("./"):
            return "local"
        if self.value.startswith("docker://"):
            return "docker"
        if self.value.startswith(FIRST_PARTY):
            return "first-party"
        name, at, ref = self.value.partition("@")
        if not at or not ref or name.count("/") < 1 or not all(name.split("/")):
            return "malformed"
        return "third-party"

    @property
    def name(self) -> str:
        return self.value.partition("@")[0]

    @property
    def ref(self) -> str:
        return self.value.partition("@")[2]

    @property
    def comment(self) -> str:
        """The comment after the value, without ``#`` and surrounding blanks."""
        return self.rest.strip().removeprefix("#").strip()


def workflow_files(repo: Path) -> tuple[list[Path], list[Path]]:
    """(files GitHub runs or calls, workflow files in subdirectories GitHub ignores)."""
    gh = repo / ".github"
    wf = gh / "workflows"
    files: list[Path] = []
    dead: list[Path] = []
    if wf.is_dir():
        for p in sorted(wf.rglob("*")):
            if p.is_file() and p.suffix in (".yml", ".yaml"):
                (files if p.parent == wf else dead).append(p)
    # Composite actions: .github/actions/<name>/ and, as in wamp-cicd, actions/<name>/ at the
    # root. A submodule's copy (.cicd/actions/ in a member) is its own repository's business.
    for actions in (gh / "actions", repo / "actions"):
        if actions.is_dir():
            for d in sorted(actions.iterdir()):
                for fname in ("action.yml", "action.yaml"):
                    if (d / fname).is_file():
                        files.append(d / fname)
    return files, dead


def lines_of(path: Path) -> list[str]:
    """The lines of a file, split at ``\\n`` only; a ``\\r`` before it is not part of
    the line (the engine's ``line_replace`` op splits the same way)."""
    text = path.read_text(encoding="utf-8")
    return [ln.removesuffix("\r") for ln in text.split("\n")]


def scan(repo: Path) -> list[Use]:
    """Every ``uses:`` line of the target's workflows and local actions, in file order."""
    files, _dead = workflow_files(repo)
    out: list[Use] = []
    for path in files:
        rel = path.relative_to(repo).as_posix()
        for i, text in enumerate(lines_of(path), start=1):
            m = USES.match(text)
            if m:
                out.append(Use(rel, i, text, m["lead"], m["quote"], m["value"], m["rest"]))
    return out


# --- decisions (A18): a member that stays behind ------------------------------------------


class DecisionFileError(ValueError):
    """A decision file that cannot be trusted as written - never silently skipped."""


def canonical_sha256(value: object) -> str:
    """sha256 of the canonical JSON of ``value`` (sorted keys, no whitespace)."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def table_observation(table: dict[str, Pin], actions: list[str]) -> dict[str, dict | None]:
    """What a deviation is decided against: the table entries of the kept actions.

    When the table moves one of them, the precondition no longer holds and the
    deviation must be decided again - against the new entry.
    """
    return {
        f"actions.toml#{a}": ({"sha": table[a].sha, "version": table[a].version} if a in table else None)
        for a in sorted(actions)
    }


def _decision_key(name: str) -> tuple[str, int] | None:
    m = re.fullmatch(rf"(\d{{8}})-{DEVIATION}(?:-(\d+))?\.toml", name)
    if m is None:
        return None
    return m.group(1), int(m.group(2) or 1)


def decision_files(repo: Path) -> list[Path]:
    """``.decisions/gh-actions/<YYYYMMDD>-gh_actions_deviation[-N].toml``, oldest first."""
    folder = repo / ".decisions" / ASPECT
    if not folder.is_dir():
        return []
    keyed = [(k, p) for p in folder.iterdir() if (k := _decision_key(p.name)) is not None]
    return [p for _k, p in sorted(keyed)]


def _validate(path: Path, data: dict, supersedes: str | None) -> None:
    problems = []
    if data.get("schema") != 1:
        problems.append(f"schema {data.get('schema')!r} (expected 1)")
    if data.get("aspect") != ASPECT:
        problems.append(f"aspect {data.get('aspect')!r} (expected {ASPECT!r})")
    if data.get("type") != DEVIATION:
        problems.append(f"type {data.get('type')!r} (expected {DEVIATION!r})")
    options = data.get("options")
    if options != list(DEVIATION_OPTIONS) or data.get("answer") not in DEVIATION_OPTIONS:
        want = list(DEVIATION_OPTIONS)
        problems.append(f"options {options!r} / answer {data.get('answer')!r} (expected options {want})")
    if data.get("decided_by") != "human":
        problems.append("a deviation must be decided_by = 'human'")
    keep = data.get("keep")
    if not isinstance(keep, list) or not keep:
        problems.append("no [[keep]] entries")
    else:
        for i, k in enumerate(keep):
            if not isinstance(k, dict):
                problems.append(f"keep[{i}] is not a table")
                continue
            if not (isinstance(k.get("action"), str) and k["action"].count("/") == 1):
                problems.append(f"keep[{i}]: action {k.get('action')!r} is not <owner>/<repo>")
            if not (isinstance(k.get("sha"), str) and SHA.fullmatch(k["sha"])):
                problems.append(f"keep[{i}]: sha {k.get('sha')!r} is not a full 40-hex commit")
            if not (isinstance(k.get("version"), str) and VERSION.fullmatch(k["version"])):
                problems.append(f"keep[{i}]: version {k.get('version')!r} is not vMAJOR.MINOR.PATCH")
            if not (isinstance(k.get("reason"), str) and k["reason"].strip()):
                problems.append(f"keep[{i}]: no reason")
    pre = (data.get("precondition") or {}).get("sha256") if isinstance(data.get("precondition"), dict) else None
    if not (isinstance(pre, str) and re.fullmatch(r"[0-9a-f]{64}", pre)):
        problems.append("no [precondition] sha256")
    if data.get("supersedes") != supersedes:
        problems.append(f"supersedes {data.get('supersedes')!r} (expected {supersedes!r})")
    if problems:
        msg = f"{path.name}: " + "; ".join(problems)
        raise DecisionFileError(msg)


def current_deviation(repo: Path) -> tuple[Path, dict] | None:
    """The current deviation decision: the NEWEST file, validated (raises
    :class:`DecisionFileError`). Newest wins strictly; an older file is history."""
    files = decision_files(repo)
    if not files:
        return None
    data: dict = {}
    for i, path in enumerate(files):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            msg = f"{path.name}: not a readable TOML decision file: {exc}"
            raise DecisionFileError(msg) from exc
        _validate(path, data, files[i - 1].name if i else None)
    return files[-1], data


def kept(repo: Path, table: dict[str, Pin]) -> tuple[dict[str, Pin], list[str]]:
    """``({action: the pin a deviation keeps}, problems)``.

    Empty when there is no decision or its answer is ``follow``. A decision whose
    precondition no longer matches the table keeps nothing and is a problem: the table
    moved since, so the deviation must be decided again.
    """
    try:
        cur = current_deviation(repo)
    except DecisionFileError as exc:
        return {}, [str(exc)]
    if cur is None:
        return {}, []
    path, data = cur
    if data["answer"] != "keep":
        return {}, []
    actions = [k["action"] for k in data["keep"]]
    if canonical_sha256(table_observation(table, actions)) != data["precondition"]["sha256"]:
        return {}, [
            f"{path.name}: decided against table entries that have changed since "
            f"({', '.join(sorted(actions))}) - decide again"
        ]
    return {k["action"]: Pin(k["sha"], k["version"]) for k in data["keep"]}, []


def open_decision_files(repo: Path) -> list[str]:
    """Repo-relative paths of ``.decisions/gh-actions/OPEN-*.toml``: a question asked
    and not yet answered. While one exists, the reconciliation stops by design."""
    folder = repo / ".decisions" / ASPECT
    if not folder.is_dir():
        return []
    return sorted(p.relative_to(repo).as_posix() for p in folder.glob("OPEN-*.toml"))
