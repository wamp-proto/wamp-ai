---
name: gh-actions
description: Which commit of each third-party GitHub Action a WAMP-family repository's workflows run - one SHA-pinned table in wamp-ai, checked and reconciled in every member. Use to check or reconcile a repository's workflows, or to bump an action in the table.
---

# gh-actions

The contract for the GitHub Actions a repository's workflows use. A tag such as `@v4` can
be moved by the action's owner at any time, so what a workflow runs is whatever the tag
points to that day. This aspect pins every third-party action to a commit, from one table,
so that all members run the same code and a change of it is a reviewed commit here.

## Rule 1: the pins (implemented)

`references/actions.toml` holds one entry per action repository:

```toml
[action."actions/checkout"]
sha     = "3d3c42e5aac5ba805825da76410c181273ba90b1"
version = "v7.0.1"
```

In a member, every third-party `uses:` line must read exactly

```yaml
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
```

| what | where | how it is handled |
|---|---|---|
| third-party action, in the table | `.github/workflows/*.yml`, `.github/actions/*/action.yml` | pinned: `line_replace` of that line |
| third-party action, not in the table | same | FAIL, no op: add it to the table first |
| action in a subdirectory of its repo (`github/codeql-action/init`) | same | the entry of its repository |
| reusable workflow of another owner (`owner/repo/.github/workflows/x.yml@ref`) | same | pinned like an action |
| local action or workflow (`./...`) | same | skipped |
| first-party (`wamp-proto/wamp-cicd/...@main`) | same | skipped: called `@main` on purpose, and wamp-cicd pins its own actions |
| `docker://` image | same | WARN: out of scope |
| workflow in a subdirectory of `.github/workflows/` | e.g. `.old/` | WARN: GitHub does not run it; not checked |

The file is read line by line, not parsed as YAML, and a reconcile changes exactly the
`uses:` lines and no other byte. A `uses:` key must start its line (after indentation and
an optional `- `), which is how every workflow writes it.

**The desired pins come from the wamp-ai checkout the aspect runs from.** Run from a
member's own `.ai` pin (`just check-aspect`), the check asks whether the workflows match
the wamp-ai that member pins. A rollout runs the reconcile from a newer wamp-ai and moves
both together: the `.ai` pin and the `uses:` lines.

## Bumping an action: the decision is made here, once

Changing an entry in `references/actions.toml` is the decision for every member:

1. `python3 aspects/gh-actions/scripts/latest.py` lists the entries that are behind, with
   the table lines for the newest releases.
2. A minor or patch bump within the major: copy the lines, commit.
3. A new major: read its release notes, name the breaking changes in the commit message,
   and say how they were verified. A path that only runs on GitHub (a release, a
   `workflow_run` trigger, Pages) needs a real run, not only a pull request's CI.
4. The maintainer lands it; a rollout brings it to the members.

The members do not decide a bump again.

## Rule 2: a member that stays behind (implemented)

A member that must keep an older version of an action records a signed decision,
`.decisions/gh-actions/<YYYYMMDD>-gh_actions_deviation[-N].toml`:

```toml
schema     = 1
aspect     = "gh-actions"
type       = "gh_actions_deviation"
question   = "Keep actions/setup-node at v4.4.0 instead of the table's v7.1.0?"
options    = ["keep", "follow"]
answer     = "keep"
decided_by = "human"

[[keep]]
action  = "actions/setup-node"
sha     = "49933ea5288caeca8642d1e84afbd3f7d6820020"
version = "v4.4.0"
reason  = "the docs build needs Node 18 until <issue>"

[precondition]
paths  = ["actions.toml#actions/setup-node"]
sha256 = "<sha256 of the table entries of the kept actions>"
```

- The newest file is the current decision; each later file names its predecessor in
  `supersedes`. `answer = "follow"` ends the deviation.
- The precondition binds the decision to the table entries it deviates from (the canonical
  JSON of `{"actions.toml#<action>": {"sha", "version"}}`, sorted). When the table moves
  one of them, the decision is stale: the check fails until it is decided again.
- `.decisions/gh-actions/OPEN-*.toml` is a question nobody has answered yet: the check
  fails and the reconcile waits (rule 3). The aspect itself never asks one: its reconcile
  always returns `decisions_required = []`.

## Scripts

Standalone, standard library only (Python 3.11+), importing nothing from any engine:

- `scripts/check.py <repo>...`: findings per repository; exit 1 on any FAIL. Offline.
- `scripts/reconcile.py --json <repo>...`: the ChangeSet, `line_replace {path, line, old,
  new}` per unpinned line, sorted, with a digest. Offline.
- `scripts/latest.py [--json] [--exit-code]`: the pin table against the newest releases,
  read with `git ls-remote --tags`. Not part of the interface; it is the only one that
  touches the network. wamp-ai runs it weekly (`.github/workflows/gh-actions-latest.yml`)
  and keeps one tracking issue open while the table is behind.
