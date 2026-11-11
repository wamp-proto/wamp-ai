Issue:    wamp-proto/wamp-ai#44
Title:    New aspect `gh-actions`: one SHA-pinned table of GitHub Actions versions, checked and reconciled in every member repo
URL:      https://github.com/wamp-proto/wamp-ai/issues/44
State:    OPEN at freeze
Author:   @oberstet
Updated:  2026-11-11T19:02:48Z
Comments: 0
Frozen:   2026-11-11T19:04:06Z by `just new-branch`
SHA-256:  43e13e987b56cf3bdf417be72e44a78419f1c2121de78cbdede8ef6e0c04f6d2 (of everything below the line)

---

## Problem

The repos' GitHub workflows use third-party actions at different versions, and most are not current. Every CI job warns that `actions/checkout@v4`, `astral-sh/setup-uv@v6` and `extractions/setup-crate` (pulled in by `extractions/setup-just@v3`) target Node 20, which GitHub has deprecated.

crossbario/autobahn-crossbar-ai#24 has the inventory and the design for the WAMP Python repos and autobahn-js. Its findings, in short:

- **Versions differ between repos.** Everyone is on `checkout` v4. `setup-uv` is v6 and `setup-just` v3 everywhere except autobahn-python (v10.0.1 and v4). Most other actions are one or more majors behind.
- **The pinning style differs:** major tags (`@v4`), a branch (`release/v1`), an exact version (`@v10.0.1`), and SHAs (only inside wamp-cicd).
- **Dependabot runs in crossbar only.** Its grouped PR crossbario/crossbar#2391 mixes low-risk bumps with risky majors, and bypasses the issue → branch → audit-file workflow.
- **No aspect covers workflow files.**

The same holds beyond those seven repos. About 20 repos across the wamp, autobahn-crossbar and aaiare projects have workflows. So the aspect belongs here, next to `way-a`, which every repo already gets from wamp-ai, and not in autobahn-crossbar-ai, whose aspects serve the autobahn-crossbar repos only. This issue replaces crossbario/autobahn-crossbar-ai#24.

wamp-cicd's own `uses:` lines (the reusable `identifiers.yml` and the composite actions that every repo calls `@main`) were bumped and SHA-pinned in wamp-cicd#96.

## The change

Add `aspects/gh-actions/`, in the same shape as `way-a`:

1. **`references/actions.toml`, one pin table.** For each third-party action: the full commit SHA and the exact version, e.g.

   ```toml
   [action."actions/checkout"]
   sha     = "3d3c42e5aac5ba805825da76410c181273ba90b1"
   version = "v7.0.1"
   ```

   The table is data next to the scripts. One bump of a member's `.ai` pin moves the table and the code that applies it together, and the rollout records which revision that was.

2. **`scripts/check.py`, read-only and offline.** It reads `.github/workflows/*.yml` (and `.github/actions/*/action.yml`, should a repo have local composite actions). It reports every `uses: <action>@<ref>` whose ref is not exactly `<sha> # <version>` from the table. A major tag, a branch, a short SHA or a missing version comment is a divergence. A third-party action that is not in the table is a divergence too, so a new action cannot slip in unpinned.
   - **Skipped** (neither reported nor changed): local actions (`./…`) and first-party refs (`wamp-proto/wamp-cicd/…`). These are called `@main` on purpose, and wamp-cicd pins its own actions itself.
   - **Job-level `uses:`** (a reusable workflow, `owner/repo/.github/workflows/x.yml@ref`) follows the same rule: skipped if first-party, pinned through the table otherwise.
   - **`docker://` refs** are reported as out of scope. There are none today.
   - Workflows in subdirectories of `.github/workflows/` are not run by GitHub, so they are reported as dead files, not checked. txaio's `.old/` is one.

3. **`scripts/reconcile.py`.** It rewrites only the ref and the version comment after `uses:` and leaves every other byte of a workflow file as it was. Actions not in the table are reported, not changed. When the check passes, it changes nothing.

4. **Where the major-version decision lives.** Moving an action to a new major in `actions.toml` is the decision. It is made once, here, in the wamp-ai commit that the maintainer lands. The commit message names the breaking changes of that major and how they were verified. The members do not decide it again.
   - A member that must stay behind, for example on an old major for a reason of its own, records a signed `gh_actions_deviation` decision in its own `.decisions/gh-actions/`, naming the action, the version it keeps and why. The check accepts that deviation while the decision is current.
   - `require.open_decisions`, as in the other aspects: an `OPEN-*.toml` under `.decisions/gh-actions/` fails the check.

5. **`scripts/latest.py`, the "latest" report.** It compares the table with each action's newest release and lists what is behind. It is kept out of `check.py`, so the check stays offline and deterministic.
   - It reads the newest release tag of the action, not the repo's `releases/latest`: for `github/codeql-action` that is the CLI bundle (v2.27.x), while the action's tag is v4.x.
   - It resolves each tag to its commit SHA, so a table bump can be copied from its output.
   - A weekly workflow here runs it and writes the result to the job summary. When the table is behind, it opens or updates one tracking issue in this repo. wamp-ai has no workflows yet; this is its first.
   - This replaces Dependabot's `github-actions` ecosystem. crossbar's `github-actions` block is removed when crossbar becomes a member.

6. **`aspect.toml` and `SKILL.md`** state the rules above, as `way-a` does.

7. **Tests** in `tests/`, as for the other aspects, on fixture workflow files:
   - the check passes on a pinned file and fails on each kind of divergence;
   - reconcile turns each failing fixture into a passing one and changes nothing else (byte comparison);
   - reconcile on a passing file changes nothing;
   - a current `gh_actions_deviation` decision passes; an open one fails.

## The first pin table

For the first rollout, the table holds what the Node 20 warning needs, at versions already verified:

| action | version | source |
|---|---|---|
| `actions/checkout` | v7.0.1 | SHA as in wamp-cicd#96 |
| `actions/upload-artifact` | v7.0.2 | SHA as in wamp-cicd#96 |
| `astral-sh/setup-uv` | latest v10 | autobahn-python runs v10.0.1 |
| `extractions/setup-just` | v4 | autobahn-python runs v4 |

The other actions enter the table at the major each repo runs today, pinned by SHA, so the first rollout pins them without a major bump. The risky majors follow as later table bumps, one each, with a real run of the affected path (release, `workflow_run`, Pages) before they land:
- `actions/checkout` v7 under `workflow_run`;
- `softprops/action-gh-release` v3;
- `actions/github-script` v9;
- `actions/download-artifact` v8;
- `actions/cache` v6;
- `actions/setup-node` v7.

## Members and rollout (not part of this issue)

Membership is declared in the apex (`aspects:` per repo) and rolled out per fleet. The first rollout covers the seven repos from crossbario/autobahn-crossbar-ai#24: autobahn-python, crossbar, txaio, zlmdb, cfxdb, wamp-xbr and autobahn-js. They already carry `.ai` → wamp-ai, so a rollout bumps that pin, adds `gh-actions` to `aspects.toml`, and reconciles the workflows. The other repos with workflows follow in later rollouts.

## Done when

- `aspects/gh-actions/` exists, with its pin table, check, reconcile and "latest" report, tested as above.
- `just test` passes here, and the weekly "latest" workflow has run once.
- The check, run against the seven repos at their current heads, reports the divergences listed in crossbario/autobahn-crossbar-ai#24, and reconcile fixes them in a scratch copy.

---

## Comments at freeze (0)

