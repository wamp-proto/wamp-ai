# Tooling structure

How the WAMP repositories get their shared tooling, and why the two repositories that _are_ the
shared tooling get it differently.

This document is the same file in
[wamp-proto/wamp-cicd](https://github.com/wamp-proto/wamp-cicd) and
[wamp-proto/wamp-ai](https://github.com/wamp-proto/wamp-ai).

## Three kinds of repository

| kind | which | what it is |
|---|---|---|
| **tooling source** | wamp-ai, wamp-cicd | the shared tooling itself: the AI policy and its commit hooks (wamp-ai); the branch workflow, the community files, the CI building blocks and the fleet tools (wamp-cicd) |
| **fleet definition** | wamp-fleet, autobahn-crossbar-fleet, ... | which repositories belong to a fleet, in which cohorts, and the rollouts applied to them |
| **ordinary repository** | everything else: wamp-proto, autobahn-python, crossbar, ... | uses the tooling, belongs to one fleet |

## The structure

|  | ordinary repository | tooling source (wamp-ai, wamp-cicd) |
|---|---|---|
| wamp-ai | submodule `.ai/` | `.deps/wamp-ai/` (not in wamp-ai itself) |
| wamp-cicd | submodule `.cicd/` | `.deps/wamp-cicd/` (not in wamp-cicd itself) |
| fleet definition | submodule `.fleet/` | `.deps/<definition repository>/` |
| where the pins live | git: the submodule pins | `deps.toml`, a tracked file |
| what is checked out | `git submodule update --init` | `just deps` |
| record of applied rollouts, `.waves/...` | yes | yes, identical |
| community files, drift check, lag check, branch workflow, commit hooks | yes | yes: the same checks, reading from `.deps/...` |

An ordinary repository has three submodules. A tooling source has the same three dependencies,
minus itself, as plain checkouts at pinned commits. A fleet definition is an ordinary repository
in this respect: it has `.ai/` and `.cicd/` as submodules (and no `.fleet/`: it cannot contain
itself).

## Why

**Why submodules in an ordinary repository.** A pin is part of the commit: every revision of the
repository says exactly which tooling it was made with, CI checks out the same thing a developer
has, and moving a pin is a reviewed change like any other.

**Why no submodules in a tooling source.** Every other repository pins wamp-ai and wamp-cicd. A
submodule _inside_ them is therefore cloned by every recursive checkout of every one of those
repositories, forever. And the two would pin each other, and the fleet definition pins both and
would be pinned by both:

```
<any repository>/.cicd                      wamp-cicd  @ X
<any repository>/.cicd/.fleet               wamp-fleet @ F     (older than X)
<any repository>/.cicd/.fleet/.cicd         wamp-cicd  @ X'    (older than F)
<any repository>/.cicd/.fleet/.cicd/.fleet  ...
```

Each level pins a strictly older commit, so it ends, but it gets one level deeper with every
bump, in every repository. The rule that prevents it:

> A repository that others pin as a submodule carries no submodules itself.

The one exception is a fleet definition, whose `.ai/` and `.cicd/` end the chain at depth two,
because those two carry none. So an ordinary repository, checked out recursively, looks like
this and never deeper:

```
.ai/            wamp-ai    @ the repository's pin
.cicd/          wamp-cicd  @ the repository's pin
.fleet/         definition @ the repository's pin
.fleet/.ai/     wamp-ai    @ the definition's pin   (not used by the repository)
.fleet/.cicd/   wamp-cicd  @ the definition's pin   (not used by the repository)
```

**Why `.deps/` and `deps.toml` instead.** A tooling source still depends on the other one: wamp-ai
needs wamp-cicd's branch workflow and community files, wamp-cicd needs wamp-ai's commit hooks and
policy, and both need their fleet's definition to know which rollouts they have received. So
they get them the plain way. `deps.toml` says which commit of which repository:

```toml
[wamp-ai]
url    = "https://github.com/wamp-proto/wamp-ai.git"
commit = "<full commit ID>"
```

and `just deps` makes the gitignored `.deps/<name>/` a checkout of exactly that commit. Nothing
follows a `deps.toml` inside a dependency, so this cannot recurse. A pin is still part of the
commit, CI still checks out what a developer has (it runs the same command), and moving a pin is
still a reviewed change: the three properties submodules were chosen for.

**Why the community files are copies.** `CONTRIBUTING.md`, the pull request template and
`.audit/README.md` are copied into every repository rather than linked, because the forge does
not follow a link into a submodule (or into `.deps/`): the "contributing guidelines" link on a
pull request would be dead. A check in CI fails when a copy differs from its template at the
pinned wamp-cicd commit. That is the same in both columns of the table; only the path of the
templates differs.

**Why the hooks need switching on.** The commit hooks are versioned, but whether they _run_ is
decided by `core.hooksPath`, which is local git configuration: not committed, not inherited by a
clone. `just where` reports whether they are enforced, and `just new-branch` refuses to start
work in a clone where they are not.

## Working in a tooling source

```bash
just deps                                   # make .deps/ what deps.toml says (after clone, after a pull)
just where                                  # reports hooks, signing, the branch, the audit file
```

Switching the hooks on, once per clone:

```bash
git config core.hooksPath .deps/wamp-ai/.githooks      # in wamp-cicd
git config core.hooksPath .githooks                    # in wamp-ai (its own hooks)
```

Moving a pin is an edit of `deps.toml` on a branch, then `just deps`:

```bash
bash scripts/deps.sh set wamp-ai https://github.com/wamp-proto/wamp-ai.git <full commit ID>
just deps
```

The pin of the fleet definition is not moved by hand: the fleet's rollout runner writes it, in
the same commit as the marker in `.waves/` that records the rollout - exactly where it moves the
`.fleet/` submodule in an ordinary repository.

`scripts/deps.sh` lives in wamp-cicd. A tooling source other than wamp-cicd carries a managed,
byte-identical copy: a repository cannot fetch the script that fetches its dependencies from a
dependency.

## Where things are, by layout

| what | ordinary repository | wamp-cicd | wamp-ai |
|---|---|---|---|
| commit hooks (`core.hooksPath`) | `.ai/.githooks` | `.deps/wamp-ai/.githooks` | `.githooks` |
| branch workflow (`just where`, `new-branch`, `publish`, `land`) | `import '.cicd/workflow.just'` | `import 'workflow.just'` | `import? '.deps/wamp-cicd/workflow.just'` |
| community file templates | `.cicd/templates/` | `templates/` | `.deps/wamp-cicd/templates/` |
| fleet definition | `.fleet/` | `.deps/<definition repository>/` | `.deps/<definition repository>/` |
| lag check in CI | `lag-check.sh` | `lag-check.sh --fleet-dir .deps/<definition repository>` | the same |

The tools find out which layout they are in by looking: `.ai/` present, else wamp-ai pinned in
`deps.toml`, else the repository's own `.githooks/`. Nothing has to be configured.
