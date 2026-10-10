---
name: way-a
description: How a WAMP-family repository is worked on - its tooling pins (wamp-ai, wamp-cicd), branch workflow, hooks, AI policy, community files, audit and CI. Use to check or reconcile a repository against that contract.
---

# way-a

The contract for how a repository is worked on. Every repository in the WAMP family declares this
aspect. It is the aspect that makes the shared tooling arrive, at the right revision, in the right
place.

## Rule 1: the tooling pins (implemented)

A repository pins **wamp-ai** (AI policy, commit hooks) and **wamp-cicd** (branch workflow, community
files, CI building blocks) at **exactly** the desired commits, in the place its layout says
(TOOLING-STRUCTURE.md):

| layout | which repositories | where the pins live |
|---|---|---|
| ordinary repository | everything that is not pinned by others | submodules `.ai` and `.cicd` |
| pinned repository | the tooling sources (wamp-ai, wamp-cicd) and every aspect repository | `deps.toml` entries, checked out in `.deps/` |

A repository is **pinned** when it has a `deps.toml`, declares the `aspect-repo` aspect, or is
wamp-cicd. A repository never depends on itself: wamp-ai has no wamp-ai entry, wamp-cicd no wamp-cicd
entry.

**The desired commits come from the wamp-ai checkout the aspect runs from:**

- desired wamp-ai = that checkout's commit (the provider revision a rollout records);
- desired wamp-cicd = the commit that checkout's `deps.toml` pins.

So moving the whole family to a new wamp-cicd is one reviewed, signed change in wamp-ai - its
`deps.toml` - followed by one rollout. Nothing is looked up on the network, and the answer is
reproducible from the rollout record.

**way-a owns these pins.** A pin is moved to exactly the desired commit, never left ahead: a pin moved
by hand outside a rollout is drift, and the next rollout puts it back.

**What is deterministic, what needs a human:**

| situation | kind | what happens |
|---|---|---|
| a pin is absent, or at another commit, or with a non-canonical URL | deterministic | `submodule_pin` or `deps_pin`, to exactly the desired commit and canonical URL |
| submodules `.ai`/`.cicd` in a pinned repository | needs a deliberate change | reported (`layout: FAIL`), no op: converting a layout is not a pin move |
| the target is this wamp-ai itself | - | nothing: its `deps.toml` is the source |

## Scripts

Standalone, standard library only (Python 3.11+), importing nothing from any engine:

- `scripts/check.py <repo>...` - findings per repository; exit 1 on any FAIL. `just check-aspect`
  (wamp-cicd) runs it from the repository's own pin of wamp-ai.
- `scripts/reconcile.py --json <repo>...` - the ChangeSet: `submodule_pin {path, url, rev}` or
  `deps_pin {path: deps.toml, name, url, commit}`, sorted, with a digest.

## Rules to come

See wamp-proto/wamp-ai#31: the CI step running `just check-aspect`; community files; hooks
switched on; the audit-file workflow; one-line `just` recipe descriptions (the last comment line
above a recipe is what `just --list` shows).

More on rule 1: [references/tooling-pins.md](references/tooling-pins.md).
