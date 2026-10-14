---
name: aspect-repo
description: >-
  What an aspect repository looks like: every aspects/<name>/ has SKILL.md with valid
  frontmatter, an aspect.toml whose name, provider and requires check out, and a
  check.py/reconcile.py interface that uses only the standard library, no network, and
  gives the same output twice. Use to check an aspect repository, or an aspect before
  it is rolled out.
---

# aspect-repo

The contract for a repository that **provides** aspects. An aspect is defined once, in
its provider, as an Agent Skill: `aspects/<name>/` with an authoritative `SKILL.md`
(plus `references/`), a machine-readable `aspect.toml`, and two scripts that rollouts
and `just check-aspect` call. This aspect checks that every aspect folder keeps that
shape, so that a rollout can trust what it runs.

Declaring `aspect-repo` also makes a repository **pinned** (way-a rule 1): its tooling
comes through `deps.toml`/`.deps`, never submodules.

## Rule 1: the aspect folder contract (implemented, check only)

`check.py <repo>` checks every directory under `aspects/` (hidden ones, and ones
starting with `_`, are skipped):

| # | rule | check | severity |
|---|---|---|---|
| 1 | `frontmatter` | `SKILL.md` exists; frontmatter starts at byte 0 with `---`, closes with a `---` line, has `name` and `description`; the body is not empty | FAIL |
| 2 | `skill-name` | frontmatter `name` equals the folder name | FAIL |
| 3 | `aspect-toml` | `aspect.toml` parses; `name` equals the folder name; `provider` equals the repository's name | FAIL |
| 4 | `requires` | every `requires` entry names an aspect of this repository, or of an aspect repository it pins in `deps.toml` (read from `.deps/`) | FAIL |
| 5 | `interface` | `scripts/check.py` and `scripts/reconcile.py` exist | FAIL |
| 6 | `stdlib-only` | the interface imports only the standard library (`sys.stdlib_module_names`) or the aspect's own `scripts/` modules | FAIL |
| 7 | `no-network` | the interface imports none of `socket`, `ssl`, `http`, `urllib`, `ftplib`, `smtplib`, `asyncio` | FAIL |
| 8 | `deterministic` | `reconcile.py --json <the aspect repository>` run twice: the same output and the same exit status | FAIL |
| 9 | `machine-local-paths` | no `/home/<user>/` or `/Users/<user>/` path in any file of the aspect folder | FAIL |
| 10 | `aspects-present` | the repository has no aspect folder at all | WARN |

**Check only.** What rule 1 finds is work for the aspect's author, not a mechanical op:
`SKILL.md` and `references/` are authoritative, and the scripts are materialized from
them. So `reconcile.py` always returns an empty ChangeSet; `check.py` reports, and CI
(`just check-aspect`) makes it visible.

**The interface** is `check.py`, `reconcile.py` and the local modules they import,
transitively. Checks 6 and 7 cover only the interface: other files in `scripts/` (a
maintenance tool, say) and other folders (a `.parked/` draft) are the author's business.

**What checks 6-8 cannot see.** `subprocess` is allowed: an interface may need to read
the target's own git history. With no network module imported, a `git` call reads local
state by intent - but a `git` call to a remote through `subprocess` passes check 7, and
check 8 catches nondeterminism only when it shows within two runs. The checks narrow the
interface; they do not prove it network-free.

**The repository's name** (check 3) comes from its GitHub remote(s) if it has any,
otherwise from its directory name. So a collaborator's clone in `<name>-<owner>` with a
GitHub remote is not reported; a clone with neither is.

**Frontmatter is read without a YAML library**, as the interface must be stdlib-only:
`key: value`, a quoted value, or a block value (`>-`, `>`, `|-`, `|`) followed by
indented lines. Anything outside that subset is a FAIL that names the line.

**No aspect yet is a WARN**, because declaring `aspect-repo` already has a consequence
(the pinned layout) before the first aspect is written. The WARN keeps an empty aspect
repository visible without turning CI red over planned work.

## Scripts

Standalone, standard library only (Python 3.11+), importing nothing from any engine:

- `scripts/check.py <repo>...` - findings per repository; exit 1 on any FAIL.
- `scripts/reconcile.py --json <repo>...` - the ChangeSet: always empty, with a digest.
- `scripts/_ar.py` - the shared logic.

## Rules to come

A short description (the description is paid for in every agent turn), and a drift
check between the authoritative prose and the materialized scripts.
