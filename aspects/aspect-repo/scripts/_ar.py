###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Shared logic of the ``aspect-repo`` aspect, rule 1: the aspect folder contract.

Standalone and stdlib-only (Python 3.11+); imports nothing from any engine.

Every ``aspects/<name>/`` of an aspect repository is checked for: SKILL.md frontmatter,
``aspect.toml``, ``requires`` that resolve, the interface (``check.py``, ``reconcile.py``)
present, standard library only and no network in the interface, a deterministic
``reconcile.py``, and no machine-local paths. A repository with no aspect folder yet is
a WARN, not a FAIL: declaring ``aspect-repo`` already makes it a pinned repository.

The rule is CHECK ONLY. A missing or malformed piece is work for an author (SKILL.md
and ``references/`` are authoritative; the scripts are materialized from them), not a
mechanical op, so ``reconcile.py`` always returns an empty ChangeSet.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

OK, WARN, FAIL = "OK", "WARN", "FAIL"

# The interface: the two scripts a rollout and `just check-aspect` call.
INTERFACE = ("check.py", "reconcile.py")

# Standard-library modules that reach the network. A check or a plan that depends on
# the network cannot be reproduced from the rollout record.
NETWORK = frozenset({"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "asyncio"})

# A path that only exists on one machine. `[a-z0-9_-]` cannot match a placeholder
# such as `/home/<user>/`, which is how documentation names the pattern.
MACHINE_LOCAL = re.compile(r"/home/[a-z0-9_-]+/|/Users/[A-Za-z0-9_.-]+/")

# How long one reconcile.py run may take before it counts as not deterministic.
RECONCILE_TIMEOUT = 120

_GITHUB = re.compile(r"github\.com[:/][^/\s]+/([^/\s]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class Finding:
    rule: str
    status: str
    message: str


# --- SKILL.md frontmatter -------------------------------------------------------------


class FrontmatterError(ValueError):
    """The frontmatter is outside the subset this parser reads."""


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Return (fields, body) of a SKILL.md, or raise FrontmatterError.

    The subset aspects use, read without a YAML library: ``key: value``, a quoted
    value, and a block value (``>-``, ``>``, ``|-``, ``|``) followed by indented lines.
    Anything else is an error that names the line - never a silent misread.
    """
    if not text.startswith("---\n"):
        raise FrontmatterError("must start with '---' at byte 0")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise FrontmatterError("frontmatter is not closed by a '---' line")
    lines = text[4:end].split("\n") if end > 3 else []
    body = text[end + 5 :]
    fields: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        lineno = i + 2  # line 1 is the opening ---
        if not line.strip():
            i += 1
            continue
        m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*))?", line)
        if not m:
            raise FrontmatterError(f"line {lineno}: not 'key: value': {line!r}")
        key, value = m.group(1), (m.group(2) or "").strip()
        if key in fields:
            raise FrontmatterError(f"line {lineno}: duplicate key {key!r}")
        if value in (">", ">-", "|", "|-"):
            block = []
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            if value.startswith(">"):
                fields[key] = " ".join(b for b in block if b)
            else:
                fields[key] = "\n".join(block).strip("\n")
            continue
        if not value:
            raise FrontmatterError(f"line {lineno}: {key!r} has no value (nested mappings are not supported)")
        if value[0] in "\"'":
            if len(value) < 2 or value[-1] != value[0]:
                raise FrontmatterError(f"line {lineno}: unterminated quoted value for {key!r}")
            value = value[1:-1]
        fields[key] = value
        i += 1
    return fields, body


# --- the repository ---------------------------------------------------------------------


def repo_names(repo: Path) -> set[str]:
    """The repository's name: from its GitHub remote(s) if any, else its directory name.

    A collaborator's clone may live in ``<name>-<owner>``; its GitHub remote still
    says ``<name>``. Without a GitHub remote, the directory name is all there is.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo), "remote", "-v"], capture_output=True, text=True, check=False
    )
    names = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            m = _GITHUB.search(parts[1])
            if m:
                names.add(m.group(1))
    return names or {repo.resolve().name}


def aspect_dirs(repo: Path) -> list[Path]:
    """The aspect folders: every non-hidden directory directly under ``aspects/``."""
    root = repo / "aspects"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def known_aspects(repo: Path) -> tuple[set[str], list[str]]:
    """Aspect names a ``requires`` may name: this repository's, and its pinned deps'.

    Returns (names, problems); a problem is a ``deps.toml`` entry whose ``.deps/``
    checkout is missing, so its aspects cannot be read.
    """
    names = {p.name for p in aspect_dirs(repo)}
    problems = []
    deps = repo / "deps.toml"
    if deps.is_file():
        try:
            entries = tomllib.loads(deps.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            return names, [f"deps.toml does not parse: {exc}"]
        for dep in sorted(entries):
            checkout = repo / ".deps" / dep
            if not checkout.is_dir():
                problems.append(f".deps/{dep} is not checked out (run: just deps)")
                continue
            names |= {p.name for p in aspect_dirs(checkout)}
    return names, problems


# --- the interface --------------------------------------------------------------------


def _imports(path: Path) -> tuple[set[str], set[str]]:
    """(absolute top-level module names, relative module names) imported by a file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    absolute, relative = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                absolute.add(node.module.split(".")[0])
            elif node.module:
                relative.add(node.module.split(".")[0])
            else:
                relative |= {a.name for a in node.names}
    return absolute, relative


def interface_imports(scripts: Path) -> tuple[dict[str, set[str]], list[str]]:
    """Every file of the interface (the two scripts and the local modules they import,
    transitively) mapped to the non-local top-level modules it imports.

    Returns (imports by file, problems); a problem is a file that does not parse.
    """
    local = {p.stem for p in scripts.glob("*.py")}
    todo = [scripts / name for name in INTERFACE if (scripts / name).is_file()]
    seen: dict[str, set[str]] = {}
    problems = []
    while todo:
        path = todo.pop()
        if path.name in seen:
            continue
        try:
            absolute, relative = _imports(path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"{path.name} does not parse: {exc}")
            seen[path.name] = set()
            continue
        seen[path.name] = {m for m in absolute if m not in local}
        for mod in sorted((absolute & local) | (relative & local)):
            todo.append(scripts / f"{mod}.py")
    return seen, problems


def reconcile_twice(scripts: Path, repo: Path) -> str | None:
    """Run ``reconcile.py --json <repo>`` twice; None if both runs agree, else why not."""
    runs = []
    for _ in range(2):
        try:
            proc = subprocess.run(
                [sys.executable, str(scripts / "reconcile.py"), "--json", str(repo)],
                capture_output=True, text=True, check=False, timeout=RECONCILE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return f"reconcile.py --json did not finish within {RECONCILE_TIMEOUT} s"
        runs.append((proc.returncode, proc.stdout))
    (rc1, out1), (rc2, out2) = runs
    if rc1 != rc2:
        return f"reconcile.py --json exited {rc1}, then {rc2}"
    if out1 != out2:
        return "reconcile.py --json gave different output on two runs"
    return None


# --- the rule -------------------------------------------------------------------------


def _text_files(folder: Path) -> list[Path]:
    out = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            out.append(p)
    return out


def inspect_aspect(repo: Path, folder: Path, names: set[str], known: set[str],
                   known_problems: list[str]) -> list[Finding]:
    """The rule-1 findings for one aspect folder."""
    a = folder.name
    out: list[Finding] = []

    # 1, 2: SKILL.md
    skill = folder / "SKILL.md"
    if not skill.is_file():
        out.append(Finding("frontmatter", FAIL, f"{a}: no SKILL.md"))
    else:
        try:
            fm, body = parse_frontmatter(skill.read_text(encoding="utf-8"))
        except (FrontmatterError, UnicodeDecodeError) as exc:
            out.append(Finding("frontmatter", FAIL, f"{a}: SKILL.md frontmatter: {exc}"))
        else:
            missing = [k for k in ("name", "description") if not fm.get(k)]
            if missing:
                out.append(Finding("frontmatter", FAIL, f"{a}: SKILL.md frontmatter lacks {', '.join(missing)}"))
            elif not body.strip():
                out.append(Finding("frontmatter", FAIL, f"{a}: SKILL.md has no body after the frontmatter"))
            else:
                out.append(Finding("frontmatter", OK, f"{a}: SKILL.md frontmatter"))
            if fm.get("name") and fm["name"] != a:
                out.append(Finding("skill-name", FAIL, f"{a}: SKILL.md name {fm['name']!r} is not the folder name"))

    # 3, 4: aspect.toml
    toml_path = folder / "aspect.toml"
    if not toml_path.is_file():
        out.append(Finding("aspect-toml", FAIL, f"{a}: no aspect.toml"))
    else:
        try:
            spec = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            out.append(Finding("aspect-toml", FAIL, f"{a}: aspect.toml does not parse: {exc}"))
        else:
            problems = []
            if spec.get("name") != a:
                problems.append(f"name {spec.get('name')!r} is not the folder name")
            if spec.get("provider") not in names:
                problems.append(f"provider {spec.get('provider')!r} is not this repository ({', '.join(sorted(names))})")
            for p in problems:
                out.append(Finding("aspect-toml", FAIL, f"{a}: aspect.toml {p}"))
            if not problems:
                out.append(Finding("aspect-toml", OK, f"{a}: aspect.toml"))
            requires = spec.get("requires", [])
            if not isinstance(requires, list) or not all(isinstance(r, str) for r in requires):
                out.append(Finding("requires", FAIL, f"{a}: requires must be a list of aspect names"))
            else:
                dangling = [r for r in requires if r not in known]
                if dangling:
                    why = f" ({'; '.join(known_problems)})" if known_problems else ""
                    out.append(Finding("requires", FAIL, f"{a}: requires names no known aspect: {', '.join(dangling)}{why}"))
                else:
                    out.append(Finding("requires", OK, f"{a}: requires {requires or 'nothing'}"))

    # 5, 6, 7, 8: the interface
    scripts = folder / "scripts"
    absent = [n for n in INTERFACE if not (scripts / n).is_file()]
    if absent:
        out.append(Finding("interface", FAIL, f"{a}: no scripts/{' or scripts/'.join(absent)}"))
    else:
        out.append(Finding("interface", OK, f"{a}: scripts/check.py and scripts/reconcile.py"))
        imports, problems = interface_imports(scripts)
        stdlib_ok, network_ok = not problems, True
        for p in problems:
            out.append(Finding("stdlib-only", FAIL, f"{a}: {p}"))
        for fname in sorted(imports):
            foreign = sorted(m for m in imports[fname] if m not in sys.stdlib_module_names)
            if foreign:
                stdlib_ok = False
                out.append(Finding("stdlib-only", FAIL, f"{a}: scripts/{fname} imports {', '.join(foreign)} (not the standard library)"))
            network = sorted(m for m in imports[fname] if m in NETWORK)
            if network:
                network_ok = False
                out.append(Finding("no-network", FAIL, f"{a}: scripts/{fname} imports {', '.join(network)} (network)"))
        files = ", ".join(sorted(imports))
        if stdlib_ok:
            out.append(Finding("stdlib-only", OK, f"{a}: the interface ({files}) imports only the standard library"))
        if network_ok:
            out.append(Finding("no-network", OK, f"{a}: the interface imports no network module"))
        why = reconcile_twice(scripts, repo)
        if why:
            out.append(Finding("deterministic", FAIL, f"{a}: {why}"))
        else:
            out.append(Finding("deterministic", OK, f"{a}: reconcile.py --json gave the same output twice"))

    # 9: machine-local paths
    clean = True
    for p in _text_files(folder):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        m = MACHINE_LOCAL.search(text)
        if m:
            rel = p.relative_to(folder)
            out.append(Finding("machine-local-paths", FAIL, f"{a}: {rel} contains the machine-local path {m.group(0)!r}"))
            clean = False
    if clean:
        out.append(Finding("machine-local-paths", OK, f"{a}: no machine-local path"))
    return out


def inspect(repo: Path) -> list[Finding]:
    """The rule-1 findings for one repository."""
    folders = aspect_dirs(repo)
    if not folders:
        return [Finding("aspects-present", WARN, "aspect repository with no aspects yet (no folder under aspects/)")]
    names = repo_names(repo)
    known, known_problems = known_aspects(repo)
    out: list[Finding] = []
    for folder in folders:
        out.extend(inspect_aspect(repo, folder, names, known, known_problems))
    return out
