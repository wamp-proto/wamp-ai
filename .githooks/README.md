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
Enforces `AI_POLICY.md` by rejecting commits with AI authorship attribution.
- Blocks: "Co-Authored-By: Claude", "Generated with Claude Code", etc.
- Ensures: Human developer is sole author, even when AI assisted

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
* You can verify your configuration with:

  ```bash
  git config core.hooksPath
  ```

It should output:

```
.githooks
```

---
