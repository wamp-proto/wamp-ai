# Git Hooks

This directory contains version-controlled Git hooks for this repository.
By default, Git stores hooks in `.git/hooks/`, which is not tracked and cannot be shared.
To share hooks across collaborators, we keep them in `.githooks/` and tell Git to use this directory instead.

## Usage

After cloning the repository, run the following command once:

```bash
git config core.hooksPath .githooks
````

This tells Git to run hooks from `.githooks/` instead of `.git/hooks/`.

## Available Hooks

### `commit-msg`
Two rules.

**AI authorship attribution** — enforces `AI_POLICY.md`.
- Blocks: "Co-Authored-By: Claude", "Generated with Claude Code", etc., on any branch
- Ensures: the human developer is sole author, even when AI assisted

**What may be committed to `main` / `master`** — only a maintainer's signed merge.
- Blocks: any ordinary commit on the integration branch
- Blocks: a merge in a repository where gitsign is not configured
- Allows: a merge in progress where `gpg.format = x509` and
  `gpg.x509.program = gitsign` — the landing step of the branch workflow
- Rationale: an approved pull request is merged locally and signed by the
  maintainer, because a merge made on the forge carries the forge's key. See
  `MERGE-AND-SIGNING-POLICY.md` in `wamp-cicd`.

This second rule is a **hint, not a control**. It runs before the commit object
exists, so it cannot check a signature — it checks what *kind* of commit this
is. Whether the merge really carries the expected identity is `pre-push`'s
question, and `gitsign verify` naming an identity and an issuer is the answer.

### `pre-push`
Prevents AI assistants from pushing Git tags (creation or deletion).
- Blocks: Pushing any refs under `refs/tags/*`
- Ensures: Tags are only created by humans on dev PC
- Rationale: Tags represent releases requiring human judgment

## Adding a New Hook

1. Add the script in this directory, using the standard Git hook name (e.g. `pre-commit`, `commit-msg`).

2. Make it executable:

   ```bash
   chmod +x .githooks/pre-commit
   ```

3. Commit and push it like any other tracked file.

## Notes

* Hooks in `.githooks/` are versioned and shared with all contributors via Git.
* Each contributor needs to run the setup step once after cloning.

### Verifying — and why `core.hooksPath` is the wrong thing to check

```bash
git config core.hooksPath          # should print .githooks (or .ai/.githooks)
ls -l "$(git config core.hooksPath)"   # and the hooks must actually BE there
```

**Check that the hook files exist and are executable, never that
`core.hooksPath` is set.** Git silently ignores a hooks directory containing no
hooks, so a repository can read as enforced and enforce nothing. That is not
hypothetical: a repository in this estate had `core.hooksPath` pointing at an
`.ai` submodule pinned to a revision where `.githooks/` was empty. Every check
had been off there for months, with no signal of any kind.

The only conclusive test is to watch a hook refuse something it should refuse.

---
