Issue:    wamp-proto/wamp-ai#46
Title:    gh-actions: reconcile.py puts file paths into decisions_required, where the fleet manager expects questions
URL:      https://github.com/wamp-proto/wamp-ai/issues/46
State:    OPEN at freeze
Author:   @oberstet
Updated:  2026-11-11T20:08:47Z
Comments: 0
Frozen:   2026-11-11T20:09:48Z by `just new-branch`
SHA-256:  6cbcc068a4db7b512086221b834e1ad63e161af8b4ae943eb8fd613df095880c (of everything below the line)

---

## What happens

The rollout engine (the AAIARE fleet manager) reads `decisions_required` from an aspect's `reconcile.py --json` as a list of questions. Each is a mapping with `type`, `question`, `options`, `decided_by`, `observed` and `precondition`, and the engine writes one `.decisions/<aspect>/OPEN-*.toml` per question. python-package emits it that way.

The gh-actions reconcile from #44 instead lists the paths of `.decisions/gh-actions/OPEN-*.toml` files that already exist:

```python
"decisions_required": pending,  # ["...OPEN-....toml"], strings
```

A rollout over a member with such a file would hand those strings to the engine, which calls `.get()` on them and fails with `AttributeError`. No member has such a file today, and gh-actions never asks a question, so nothing has failed yet. The output is still wrong, and the aspect-repo check cannot see it.

## The change

1. `reconcile.py` always returns `decisions_required: []`. gh-actions asks no questions: a bump is decided in the pin table, and a member that stays behind writes its `gh_actions_deviation` decision itself.
2. While an `OPEN-*.toml` exists under `.decisions/gh-actions/`, the ChangeSet stays empty, as now. The check keeps failing on it (rule 3), which is where a human sees it.
3. `SKILL.md` and the module docstring say so.

## Test

- With an `OPEN-*.toml` present: `changeset == []` and `decisions_required == []`, and the check FAILs on `open-decisions`.
- In every other test, `decisions_required` is `[]`.
- `just test` passes.

---

## Comments at freeze (0)

