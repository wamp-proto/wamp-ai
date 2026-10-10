###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Tests for the way-a aspect, rule 1: the tooling pins (wamp-proto/wamp-ai#31).

Real git repositories in a temp directory, both layouts, every state: absent, right,
wrong commit, wrong URL, and the layout problem that must not become a pin move. The
desired commits come from this checkout of wamp-ai (``_wa.desired()``), exactly as in a
rollout. Standard library only: ``python3 -m unittest discover -s tests``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "aspects" / "way-a" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _wa  # noqa: E402
from check import inspect_repo  # noqa: E402
from reconcile import reconcile_repo  # noqa: E402

WANT = _wa.desired()
OLD = "0" * 39 + "1"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(root: Path, name: str, files: dict[str, str] | None = None) -> Path:
    repo = root / name
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    for rel, text in (files or {}).items():
        (repo / rel).write_text(text, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    return repo


def add_gitlink(repo: Path, path: str, rev: str, url: str) -> None:
    git(repo, "config", "-f", ".gitmodules", f"submodule.{path}.path", path)
    git(repo, "config", "-f", ".gitmodules", f"submodule.{path}.url", url)
    git(repo, "add", ".gitmodules")
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{rev},{path}")
    git(repo, "commit", "-q", "-m", f"pin {path}")


def deps(ai: str | None, cicd: str | None) -> str:
    out = ""
    for name, commit in (("wamp-ai", ai), ("wamp-cicd", cicd)):
        if commit:
            out += f'[{name}]\nurl    = "{_wa.URLS[name]}"\ncommit = "{commit}"\n\n'
    return out


def statuses(repo: Path) -> list[tuple[str, str]]:
    return [(f.rule, f.status) for f in inspect_repo(repo)]


class Ordinary(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_absent_pins_fail_and_reconcile_adds_both(self) -> None:
        repo = make_repo(self.root, "lib")
        self.assertEqual(statuses(repo), [("tooling-pins", "FAIL")] * 2)
        ops = reconcile_repo(repo)["changeset"]
        self.assertEqual(
            ops,
            [
                {"action": "submodule_pin", "kind": "submodule_update", "path": ".ai",
                 "url": _wa.URLS["wamp-ai"], "rev": WANT["wamp-ai"]},
                {"action": "submodule_pin", "kind": "submodule_update", "path": ".cicd",
                 "url": _wa.URLS["wamp-cicd"], "rev": WANT["wamp-cicd"]},
            ],
        )

    def test_pins_at_the_desired_commits_are_ok_and_need_nothing(self) -> None:
        repo = make_repo(self.root, "lib")
        add_gitlink(repo, ".ai", WANT["wamp-ai"], _wa.URLS["wamp-ai"])
        add_gitlink(repo, ".cicd", WANT["wamp-cicd"], _wa.URLS["wamp-cicd"])
        self.assertEqual(statuses(repo), [("tooling-pins", "OK")] * 2)
        self.assertEqual(reconcile_repo(repo)["changeset"], [])

    def test_an_old_commit_is_moved_to_exactly_the_desired_one(self) -> None:
        repo = make_repo(self.root, "lib")
        add_gitlink(repo, ".ai", OLD, _wa.URLS["wamp-ai"])
        add_gitlink(repo, ".cicd", WANT["wamp-cicd"], _wa.URLS["wamp-cicd"])
        self.assertEqual(statuses(repo), [("tooling-pins", "FAIL"), ("tooling-pins", "OK")])
        (op,) = reconcile_repo(repo)["changeset"]
        self.assertEqual((op["path"], op["rev"]), (".ai", WANT["wamp-ai"]))

    def test_a_non_canonical_url_fails_and_is_corrected(self) -> None:
        repo = make_repo(self.root, "lib")
        add_gitlink(repo, ".ai", WANT["wamp-ai"], "git@github.com:wamp-proto/wamp-ai.git")
        add_gitlink(repo, ".cicd", WANT["wamp-cicd"], _wa.URLS["wamp-cicd"])
        msgs = [f.message for f in inspect_repo(repo) if f.status == "FAIL"]
        self.assertEqual(len(msgs), 1)
        self.assertIn("url", msgs[0])
        (op,) = reconcile_repo(repo)["changeset"]
        self.assertEqual(op["url"], _wa.URLS["wamp-ai"])


class Pinned(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_old_deps_entries_are_moved_by_deps_pin(self) -> None:
        repo = make_repo(self.root, "some-ai", {"deps.toml": deps(OLD, OLD)})
        self.assertEqual(statuses(repo), [("tooling-pins", "FAIL")] * 2)
        ops = reconcile_repo(repo)["changeset"]
        self.assertEqual([(o["action"], o["name"], o["commit"]) for o in ops], [
            ("deps_pin", "wamp-ai", WANT["wamp-ai"]),
            ("deps_pin", "wamp-cicd", WANT["wamp-cicd"]),
        ])

    def test_deps_entries_at_the_desired_commits_are_ok(self) -> None:
        repo = make_repo(self.root, "some-ai", {"deps.toml": deps(WANT["wamp-ai"], WANT["wamp-cicd"])})
        self.assertEqual(statuses(repo), [("tooling-pins", "OK")] * 2)
        self.assertEqual(reconcile_repo(repo)["changeset"], [])

    def test_an_aspect_repository_is_pinned_even_without_deps_toml(self) -> None:
        repo = make_repo(self.root, "new-ai", {"aspects.toml": 'aspects = ["way-a", "aspect-repo"]\n'})
        ops = reconcile_repo(repo)["changeset"]
        self.assertEqual({o["action"] for o in ops}, {"deps_pin"})

    def test_wamp_cicd_does_not_pin_itself(self) -> None:
        repo = make_repo(self.root, "wamp-cicd", {"deps.toml": deps(WANT["wamp-ai"], None)})
        self.assertEqual(statuses(repo), [("tooling-pins", "OK")])
        self.assertEqual(reconcile_repo(repo)["changeset"], [])

    def test_submodules_in_a_pinned_repository_are_a_finding_not_a_pin_move(self) -> None:
        repo = make_repo(self.root, "some-ai", {"deps.toml": deps(WANT["wamp-ai"], WANT["wamp-cicd"])})
        add_gitlink(repo, ".ai", WANT["wamp-ai"], _wa.URLS["wamp-ai"])
        self.assertIn(("layout", "FAIL"), statuses(repo))
        self.assertEqual(reconcile_repo(repo)["changeset"], [])


class SelfAndDeterminism(unittest.TestCase):
    def test_wamp_ai_itself_needs_nothing(self) -> None:
        self.assertEqual(statuses(_wa.PROVIDER), [("tooling-pins", "OK")])
        self.assertEqual(reconcile_repo(_wa.PROVIDER)["changeset"], [])

    def test_the_changeset_and_its_digest_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), "lib")
            a, b = reconcile_repo(repo), reconcile_repo(repo)
            self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
