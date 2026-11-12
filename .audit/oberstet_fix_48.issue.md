Issue:    wamp-proto/wamp-ai#48
Title:    gh-actions: pin JamesIves/github-pages-deploy-action, check composite actions under actions/, and make wamp-ai a member itself
URL:      https://github.com/wamp-proto/wamp-ai/issues/48
State:    OPEN at freeze
Author:   @oberstet
Updated:  2026-11-12T01:04:03Z
Comments: 0
Frozen:   2026-11-12T01:04:39Z by `just new-branch`
SHA-256:  37e8315d18aa05846cf61991ef4568b083d7a6b0754d683c9411ef9d75714abf (of everything below the line)

---

## Why

The remaining `way-a` repositories with workflows are getting the `gh-actions` aspect (typedefint/aaiare-metal-typedefint, the apex change for the ten repositories). Before their rollouts, three things here:

1. **An action missing from the pin table.** wamp-proto and wamp-site-gen deploy with `JamesIves/github-pages-deploy-action@v4`. The check reports "not in the pin table", and the reconcile leaves the line alone. Their rollouts would not converge.
2. **wamp-cicd's composite actions are not checked.** They live in `actions/*/action.yml` at the repository root, not under `.github/actions/`. Every repository calls them `@main`, so their `uses:` lines run everywhere. Today there is one: `actions/upload-artifact` in `upload-artifact-verified`, pinned by hand in wamp-cicd#96 and matching the table. Nothing keeps it matching.
3. **wamp-ai is a member too.** The apex gives it `gh-actions`. If the wamp fleet's rollout committed its `aspects.toml`, wamp-ai's head would move after the other members were planned against it: the way-a pin chase. Decided for that case: the provider first.

## The change

1. `references/actions.toml`: add

   ```toml
   [action."JamesIves/github-pages-deploy-action"]
   sha     = "fa24774553152dd7873cd16ebd8d959b010c5445"
   version = "v4.9.0"
   ```

   This is the newest release of the major in use (v4), so the rollout pins it without a major bump.
2. `_gha.workflow_files()`: also read `actions/*/action.yml` / `action.yaml` at the repository root. A submodule's copy, such as `.cicd/actions/...` in a member, is not under `actions/`, so it is not read twice. The same rules apply as for `.github/actions/`.
3. `aspects.toml`: `["way-a", "gh-actions", "aspect-repo"]`, exactly as the fleet manager renders it from the apex. wamp-ai's own workflow already passes the check, so its rollout would have nothing else to do. wamp-ai is then not a rollout member, and every rollout pins this head.
4. `SKILL.md`: the table of what is read, plus `actions/*/action.yml`.

## Test

- Tests: a composite action under `actions/x/action.yml` is checked and reconciled; a `.cicd/actions/x/action.yml` in a member is not read; the shipped table has the new entry.
- `just test` passes. The aspect-repo check passes for gh-actions.
- The check passes on wamp-cicd's main (its `actions/upload-artifact-verified` included) and on wamp-ai itself.
- On wamp-proto and wamp-site-gen at their heads: no "not in the pin table" finding any more, and the reconcile's ops make the check pass in a scratch copy.
- After this lands, the fleet manager's rollout plan for the wamp fleet does not list wamp-ai.

---

## Comments at freeze (0)

