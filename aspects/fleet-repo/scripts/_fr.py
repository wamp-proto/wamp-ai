###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Shared logic of the ``fleet-repo`` aspect: the rollout records and their index.

Standalone and stdlib-only (Python 3.11+); imports nothing from any engine.

Rule 1 checks every ``rollouts/<id>/rollout.toml``: schema, id, status, fleet, commit
fields, members and their changeset hash, and what the record's status promises (a
``converged`` record carries proof of an empty ChangeSet for every member).

Rule 2 checks ``rollouts/README.md``, the index the rollout engine generates at each
close-out, for CONSISTENCY with the records: the same set of rollouts, the same aspect,
status and fleet issue per row, newest first. It does not re-render the index - the
renderer belongs to the rollout engine, and a second copy here would drift from it.

Both rules are CHECK ONLY: the records are evidence, written once by the rollout
engine, and an aspect never rewrites them. ``reconcile.py`` returns an empty ChangeSet.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

OK, WARN, FAIL = "OK", "WARN", "FAIL"

SCHEMA = 1
# In the order a rollout passes through them; a status promises what every earlier
# one promised.
STATUSES = ("planned", "issues-filed", "executed", "landed", "converged")
DECIDERS = ("human", "agent")

# The digest of the empty ChangeSet: what a converged member's proof must show.
EMPTY_CHANGESET_SHA256 = hashlib.sha256(b"[]").hexdigest()

MEMBER_REQUIRED = ("repo", "slug", "base", "changes", "changeset", "changeset_sha256")
MEMBER_COMMITS = ("base", "commit", "merge", "provider_pin", "proof_provider_rev", "proof_rev", "stop_commit")

INDEX = "README.md"
INDEX_HEADER = "<!-- Generated at each rollout close-out"

_SHA = re.compile(r"[0-9a-f]{40}")
_GITHUB = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")
_ROW = re.compile(
    r"^\| \[`(?P<id>[^`]+)`\]\((?P<link>[^)]+)/rollout\.toml\) \| `(?P<aspect>[^`]+)` \| "
    r"(?P<status>[^|]+?) \| (?P<issue>[^|]+?) \|"
)
_ISSUE = re.compile(r"\[#(\d+)\]\(")


@dataclass(frozen=True)
class Finding:
    rule: str
    status: str
    message: str


def fleet_slugs(repo: Path) -> tuple[set[str], str]:
    """(full ``org/name`` slugs from GitHub remotes, the directory name).

    With a GitHub remote, ``fleet`` must be one of its slugs. Without one, only the
    name part of ``fleet`` can be compared, with the directory name.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo), "remote", "-v"], capture_output=True, text=True, check=False
    )
    slugs = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            m = _GITHUB.search(parts[1])
            if m:
                slugs.add(f"{m.group(1)}/{m.group(2)}")
    return slugs, repo.resolve().name


def record_dirs(repo: Path) -> list[Path]:
    """The rollout folders: every ``rollouts/<id>/`` that contains a ``rollout.toml``."""
    root = repo / "rollouts"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / "rollout.toml").is_file())


# --- rule 1: one record -----------------------------------------------------------------


def inspect_record(folder: Path, slugs: set[str], dirname: str) -> tuple[list[Finding], dict | None]:
    """The rule-1 findings for one record, and the parsed record (None if it did not parse)."""
    rid = folder.name
    try:
        rec = tomllib.loads((folder / "rollout.toml").read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return [Finding("schema", FAIL, f"{rid}: rollout.toml does not parse: {exc}")], None
    if rec.get("schema") != SCHEMA:
        return [Finding("schema", FAIL, f"{rid}: schema {rec.get('schema')!r}, this aspect reads schema {SCHEMA}")], None

    out: list[Finding] = []

    # 2: id
    aspect = rec.get("aspect", "")
    if rec.get("id") != rid:
        out.append(Finding("id", FAIL, f"{rid}: id {rec.get('id')!r} is not the folder name"))
    elif not isinstance(aspect, str) or not re.fullmatch(rf"\d{{8}}-{re.escape(aspect)}(-\d+)?", rid):
        out.append(Finding("id", FAIL, f"{rid}: id is not YYYYMMDD-{aspect}[-N]"))

    # 3: status
    status = rec.get("status")
    if status not in STATUSES:
        out.append(Finding("status", FAIL, f"{rid}: status {status!r} is not one of {', '.join(STATUSES)}"))

    # 4: fleet
    fleet = rec.get("fleet", "")
    if slugs:
        if fleet not in slugs:
            out.append(Finding("fleet", FAIL, f"{rid}: fleet {fleet!r} is not this repository ({', '.join(sorted(slugs))})"))
    elif not isinstance(fleet, str) or fleet.rpartition("/")[2] != dirname:
        out.append(Finding("fleet", FAIL, f"{rid}: fleet {fleet!r} is not this repository ({dirname})"))

    # 5: provider, apex, every commit field
    provider, apex = rec.get("provider") or {}, rec.get("apex") or {}
    if not provider.get("repo"):
        out.append(Finding("revs", FAIL, f"{rid}: no [provider] repo"))
    commits = [("provider.rev", provider.get("rev")), ("apex.rev", apex.get("rev"))]
    members = rec.get("member", [])
    for m in members:
        who = m.get("repo", "?")
        commits += [(f"{who}.{k}", m[k]) for k in MEMBER_COMMITS if k in m]
        commits += [(f"{who}.decision.commit", d.get("commit")) for d in m.get("decision", [])]
    for where, value in commits:
        if not isinstance(value, str) or not _SHA.fullmatch(value):
            out.append(Finding("revs", FAIL, f"{rid}: {where} {value!r} is not a full 40-character SHA"))

    # 6: members
    for m in members:
        who = m.get("repo", "?")
        missing = [k for k in MEMBER_REQUIRED if k not in m]
        if missing:
            out.append(Finding("members", FAIL, f"{rid}: member {who} lacks {', '.join(missing)}"))
            continue
        actual = hashlib.sha256(str(m["changeset"]).encode("utf-8")).hexdigest()
        if actual != m["changeset_sha256"]:
            out.append(Finding("members", FAIL, f"{rid}: member {who}: changeset_sha256 does not match its changeset"))

    # 7: what the status promises
    if status in STATUSES:
        level = STATUSES.index(status)
        for m in members:
            who = m.get("repo", "?")
            lacks = []
            if level >= STATUSES.index("issues-filed") and "issue" not in m:
                lacks.append("issue")
            if level >= STATUSES.index("executed") and "commit" not in m and "stop_commit" not in m:
                lacks.append("commit (or stop_commit)")
            if level >= STATUSES.index("landed") and "merge" not in m:
                lacks.append("merge")
            if status == "converged":
                if "proof_rev" not in m:
                    lacks.append("proof_rev")
                if m.get("proof_changeset_sha256") != EMPTY_CHANGESET_SHA256:
                    lacks.append("proof of an empty ChangeSet")
            if lacks:
                out.append(Finding("promises", FAIL, f"{rid}: {status}, but member {who} has no {', no '.join(lacks)}"))

    # 8: decisions
    for m in members:
        for d in m.get("decision", []):
            if d.get("decided_by") not in DECIDERS:
                out.append(Finding("decisions", FAIL, f"{rid}: member {m.get('repo', '?')}: decided_by {d.get('decided_by')!r} is not one of {', '.join(DECIDERS)}"))

    if not out:
        out.append(Finding("record", OK, f"{rid}: {status}, {len(members)} member(s)"))
    return out, rec


# --- rule 2: the index ------------------------------------------------------------------


def _issue_cell(cell: str) -> int | None:
    m = _ISSUE.match(cell.strip())
    return int(m.group(1)) if m else None


def inspect_index(repo: Path, records: dict[str, dict | None]) -> list[Finding]:
    """The rule-2 findings: the index against the records."""
    path = repo / "rollouts" / INDEX
    if not path.is_file():
        return [Finding("index-header", FAIL, f"no rollouts/{INDEX} (the generated index)")]
    text = path.read_text(encoding="utf-8")
    out: list[Finding] = []
    if not text.startswith(INDEX_HEADER):
        out.append(Finding("index-header", FAIL, f"rollouts/{INDEX} does not start with its generated-file comment"))

    rows = []
    for line in text.splitlines():
        m = _ROW.match(line)
        if m:
            rows.append(m)
        elif line.startswith("| [`"):
            out.append(Finding("index-rows", FAIL, f"rollouts/{INDEX}: a row that cannot be read: {line[:80]!r}"))

    listed = [r.group("id") for r in rows]
    missing = sorted(set(records) - set(listed))
    extra = sorted(set(listed) - set(records))
    if missing:
        out.append(Finding("index-set", FAIL, f"rollouts/{INDEX} does not list: {', '.join(missing)}"))
    if extra:
        out.append(Finding("index-set", FAIL, f"rollouts/{INDEX} lists rollouts with no record: {', '.join(extra)}"))
    dupes = sorted({i for i in listed if listed.count(i) > 1})
    if dupes:
        out.append(Finding("index-set", FAIL, f"rollouts/{INDEX} lists more than once: {', '.join(dupes)}"))

    for r in rows:
        rid, rec = r.group("id"), records.get(r.group("id"))
        if r.group("link") != rid:
            out.append(Finding("index-rows", FAIL, f"{rid}: the index row links {r.group('link')}/rollout.toml"))
        if not rec:
            continue
        diffs = []
        if r.group("aspect") != rec.get("aspect"):
            diffs.append(f"aspect {r.group('aspect')!r} (record: {rec.get('aspect')!r})")
        if r.group("status").strip() != rec.get("status"):
            diffs.append(f"status {r.group('status').strip()!r} (record: {rec.get('status')!r})")
        if _issue_cell(r.group("issue")) != rec.get("fleet_issue"):
            diffs.append(f"fleet issue {r.group('issue').strip()!r} (record: {rec.get('fleet_issue')!r})")
        if diffs:
            out.append(Finding("index-rows", FAIL, f"{rid}: the index says {'; '.join(diffs)} - regenerate the index"))

    if listed != sorted(listed, reverse=True):
        out.append(Finding("index-order", FAIL, f"rollouts/{INDEX}: rows are not newest first"))

    if not out:
        out.append(Finding("index", OK, f"rollouts/{INDEX} lists the {len(records)} record(s), consistent"))
    return out


def inspect(repo: Path) -> list[Finding]:
    """The rule-1 and rule-2 findings for one fleet repository."""
    folders = record_dirs(repo)
    if not folders:
        return [Finding("rollouts-present", WARN, "fleet repository with no rollout yet (no rollouts/<id>/rollout.toml)")]
    slugs, dirname = fleet_slugs(repo)
    out: list[Finding] = []
    records: dict[str, dict | None] = {}
    for folder in folders:
        findings, rec = inspect_record(folder, slugs, dirname)
        out.extend(findings)
        records[folder.name] = rec
    out.extend(inspect_index(repo, records))
    return out
