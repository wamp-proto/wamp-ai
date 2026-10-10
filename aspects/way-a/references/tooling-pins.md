# The tooling pins - details

## Why exact, and why from wamp-ai

A tooling pin that floats ("latest main") makes two checkouts of the same commit behave differently,
and a pin each repository moves on its own drifts: measured on 2026-10-11, ten repositories pinned
three different wamp-cicd commits, and one aspect repository's `just land` lacked a guard that
wamp-cicd had shipped days earlier. An exact pin, moved only by a rollout, makes every repository a
function of one input: the wamp-ai revision the rollout used.

wamp-ai is the right place for the wamp-cicd pin because it is the provider of this aspect: the
rollout already records its revision, so the desired wamp-cicd commit is recorded too, without a
second input.

## Layout detection

1. The target is this wamp-ai checkout: self-hosting, nothing to pin.
2. `deps.toml` exists, or `aspect-repo` is declared in `aspects.toml`, or the target is wamp-cicd:
   pinned layout.
3. Otherwise: ordinary layout.

An aspect repository is detected by its declared aspects, not by guessing from its files: the first
rollout to an aspect repository without a `deps.toml` creates the file.

## What counts

The index for submodule pins (a staged pin move counts; in a clean tree that is HEAD), the working
tree for `deps.toml`: what a commit made now would contain.
