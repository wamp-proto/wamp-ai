###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Tests for the aspect-repo aspect, rule 1: the aspect folder contract (wamp-proto/wamp-ai#38).

Real git repositories in a temp directory. One conforming aspect folder, then one
fixture per check that breaks exactly one thing: that check FAILs, and nothing else.
Standard library only: ``python3 -m unittest discover -s tests``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "aspects" / "aspect-repo" / "scripts"


def _load(name: str, filename: str):
    """Load one of this aspect's scripts under a name of its own.

    NOT ``import check``: way-a's scripts are also called ``check`` and ``reconcile``,
    and whichever test module runs first would leave its own in ``sys.modules`` for the
    other (measured: ten way-a tests failed when this file ran first).
    """
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SCRIPTS))
try:
    _ar = _load("_ar", "_ar.py")
    check = _load("aspect_repo_check", "check.py")
    reconcile_repo = _load("aspect_repo_reconcile", "reconcile.py").reconcile_repo
finally:
    sys.path.remove(str(SCRIPTS))

SKILL = """---
name: demo
description: >-
  A demo aspect, folded over
  two lines.
---

# demo

What the demo contract is.
"""

CHECK = """import json
import sys

from _helper import findings

print(json.dumps(findings()))
sys.exit(0)
"""

HELPER = """import json


def findings():
    return json.loads("[]")
"""

RECONCILE = """import json

print(json.dumps({"changeset": [], "digest": "x"}))
"""


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(root: Path, dirname: str, provider: str | None = None, *, remote: str | None = None,
              aspect: bool = True) -> Path:
    """A git repository with one conforming aspect folder ``aspects/demo/``."""
    repo = root / dirname
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    if remote:
        git(repo, "remote", "add", "upstream", remote)
    if aspect:
        folder = repo / "aspects" / "demo"
        (folder / "scripts").mkdir(parents=True)
        (folder / "references").mkdir()
        (folder / "SKILL.md").write_text(SKILL, encoding="utf-8")
        (folder / "aspect.toml").write_text(
            f'name = "demo"\ndescription = "A demo."\nprovider = "{provider or dirname}"\nrequires = []\n',
            encoding="utf-8",
        )
        (folder / "references" / "notes.md").write_text("Notes, at `aspects/demo/`.\n", encoding="utf-8")
        (folder / "scripts" / "check.py").write_text(CHECK, encoding="utf-8")
        (folder / "scripts" / "_helper.py").write_text(HELPER, encoding="utf-8")
        (folder / "scripts" / "reconcile.py").write_text(RECONCILE, encoding="utf-8")
    return repo


def fails(repo: Path) -> list[str]:
    return sorted({f.rule for f in _ar.inspect(repo) if f.status == _ar.FAIL})


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = make_repo(self.root, "prov")
        self.demo = self.repo / "aspects" / "demo"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def edit(self, rel: str, text: str) -> None:
        path = self.demo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class Conforming(Base):
    def test_conforming_aspect_has_no_findings_but_ok(self) -> None:
        findings = _ar.inspect(self.repo)
        self.assertEqual([f for f in findings if f.status != _ar.OK], [])
        self.assertEqual(
            {f.rule for f in findings},
            {"frontmatter", "aspect-toml", "requires", "interface", "stdlib-only", "no-network",
             "deterministic", "machine-local-paths"},
        )

    def test_check_main_exits_zero(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(check.main([str(self.repo)]), 0)


class OneCheckEach(Base):
    """Each fixture breaks exactly one thing; exactly that check FAILs."""

    def test_1_frontmatter_leading_blank_line(self) -> None:
        self.edit("SKILL.md", "\n" + SKILL)
        self.assertEqual(fails(self.repo), ["frontmatter"])

    def test_1_frontmatter_unclosed(self) -> None:
        self.edit("SKILL.md", "---\nname: demo\ndescription: d\n# demo\n")
        self.assertEqual(fails(self.repo), ["frontmatter"])

    def test_1_frontmatter_missing_description(self) -> None:
        self.edit("SKILL.md", "---\nname: demo\n---\n\n# demo\n")
        self.assertEqual(fails(self.repo), ["frontmatter"])

    def test_1_frontmatter_empty_body(self) -> None:
        self.edit("SKILL.md", "---\nname: demo\ndescription: d\n---\n\n")
        self.assertEqual(fails(self.repo), ["frontmatter"])

    def test_1_frontmatter_outside_the_subset_names_the_line(self) -> None:
        self.edit("SKILL.md", "---\nname: demo\ndescription: d\nmetadata:\n  tags: [a]\n---\n\n# demo\n")
        self.assertEqual(fails(self.repo), ["frontmatter"])
        msg = next(f.message for f in _ar.inspect(self.repo) if f.rule == "frontmatter")
        self.assertIn("line 4", msg)

    def test_2_skill_name_not_the_folder(self) -> None:
        self.edit("SKILL.md", SKILL.replace("name: demo", "name: other"))
        self.assertEqual(fails(self.repo), ["skill-name"])

    def test_3_aspect_toml_provider_not_this_repository(self) -> None:
        text = (self.demo / "aspect.toml").read_text(encoding="utf-8").replace('"prov"', '"elsewhere"')
        self.edit("aspect.toml", text)
        self.assertEqual(fails(self.repo), ["aspect-toml"])

    def test_3_aspect_toml_name_not_the_folder(self) -> None:
        text = (self.demo / "aspect.toml").read_text(encoding="utf-8").replace('name = "demo"', 'name = "x"')
        self.edit("aspect.toml", text)
        self.assertEqual(fails(self.repo), ["aspect-toml"])

    def test_3_aspect_toml_does_not_parse(self) -> None:
        self.edit("aspect.toml", "name = \n")
        self.assertEqual(fails(self.repo), ["aspect-toml"])

    def test_4_requires_names_no_aspect(self) -> None:
        text = (self.demo / "aspect.toml").read_text(encoding="utf-8").replace("requires = []", 'requires = ["no-such-aspect"]')
        self.edit("aspect.toml", text)
        self.assertEqual(fails(self.repo), ["requires"])

    def test_5_no_reconcile_py(self) -> None:
        (self.demo / "scripts" / "reconcile.py").unlink()
        self.assertEqual(fails(self.repo), ["interface"])

    def test_6_helper_imported_by_the_interface_imports_a_third_party_module(self) -> None:
        self.edit("scripts/_helper.py", "import yaml\n\n\ndef findings():\n    return []\n")
        self.assertEqual(fails(self.repo), ["stdlib-only"])
        msg = next(f.message for f in _ar.inspect(self.repo) if f.status == _ar.FAIL)
        self.assertIn("_helper.py imports yaml", msg)

    def test_7_reconcile_imports_a_network_module(self) -> None:
        self.edit("scripts/reconcile.py", "import json\nimport urllib.request\n\nprint(json.dumps([]))\n")
        self.assertEqual(fails(self.repo), ["no-network"])

    def test_8_reconcile_not_deterministic(self) -> None:
        self.edit("scripts/reconcile.py", "import time\n\nprint(time.time_ns())\n")
        self.assertEqual(fails(self.repo), ["deterministic"])

    def test_9_machine_local_path_in_a_reference(self) -> None:
        self.edit("references/notes.md", "See /home/someone/work/thing for details.\n")
        self.assertEqual(fails(self.repo), ["machine-local-paths"])

    def test_9_a_placeholder_is_not_a_machine_local_path(self) -> None:
        self.edit("references/notes.md", "The pattern is /home/<user>/ and /Users/<user>/.\n")
        self.assertEqual(fails(self.repo), [])


class Scope(Base):
    def test_files_outside_the_interface_are_not_checked(self) -> None:
        self.edit("scripts/upstream_watch.py", "import yaml\nimport urllib.request\n")
        self.edit(".parked/draft.py", "import yaml\n")
        self.assertEqual(fails(self.repo), [])

    def test_hidden_and_underscore_folders_are_not_aspects(self) -> None:
        (self.repo / "aspects" / ".parked").mkdir()
        (self.repo / "aspects" / "_shared").mkdir()
        self.assertEqual(fails(self.repo), [])

    def test_relative_import_is_followed(self) -> None:
        self.edit("scripts/check.py", "from . import _helper\n")
        self.edit("scripts/_helper.py", "import yaml\n")
        self.assertEqual(fails(self.repo), ["stdlib-only"])


class Requires(Base):
    def _require(self, name: str) -> None:
        text = (self.demo / "aspect.toml").read_text(encoding="utf-8").replace("requires = []", f'requires = ["{name}"]')
        self.edit("aspect.toml", text)

    def _pin_dep(self) -> Path:
        (self.repo / "deps.toml").write_text(
            '[other]\nurl = "https://example.invalid/other.git"\ncommit = "' + "0" * 40 + '"\n', encoding="utf-8"
        )
        return self.repo / ".deps" / "other"

    def test_requires_resolves_in_this_repository(self) -> None:
        (self.repo / "aspects" / "base").mkdir()
        self._require("base")
        self.assertNotIn("requires", fails(self.repo))

    def test_requires_resolves_through_deps(self) -> None:
        dep = self._pin_dep()
        (dep / "aspects" / "base").mkdir(parents=True)
        self._require("base")
        self.assertEqual(fails(self.repo), [])

    def test_requires_with_deps_not_checked_out_says_so(self) -> None:
        self._pin_dep()
        self._require("base")
        self.assertEqual(fails(self.repo), ["requires"])
        msg = next(f.message for f in _ar.inspect(self.repo) if f.rule == "requires")
        self.assertIn("just deps", msg)


class RepositoryName(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_collaborator_clone_with_github_remote_is_not_a_wrong_provider(self) -> None:
        repo = make_repo(self.root, "prov-owner", "prov", remote="git@github.com:org/prov.git")
        self.assertEqual(fails(repo), [])

    def test_https_github_remote(self) -> None:
        repo = make_repo(self.root, "prov-owner", "prov", remote="https://github.com/org/prov.git")
        self.assertEqual(fails(repo), [])

    def test_collaborator_clone_without_github_remote_is_reported(self) -> None:
        repo = make_repo(self.root, "prov-owner", "prov")
        self.assertEqual(fails(repo), ["aspect-toml"])


class NoAspects(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_no_aspects_folder_is_one_warn_and_exit_zero(self) -> None:
        repo = make_repo(self.root, "prov", aspect=False)
        findings = _ar.inspect(repo)
        self.assertEqual([(f.rule, f.status) for f in findings], [("aspects-present", _ar.WARN)])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(check.main([str(repo)]), 0)

    def test_empty_aspects_folder_is_one_warn(self) -> None:
        repo = make_repo(self.root, "prov", aspect=False)
        (repo / "aspects").mkdir()
        self.assertEqual([f.status for f in _ar.inspect(repo)], [_ar.WARN])


class Frontmatter(unittest.TestCase):
    def test_folded_block(self) -> None:
        fields, body = _ar.parse_frontmatter(SKILL)
        self.assertEqual(fields["description"], "A demo aspect, folded over two lines.")
        self.assertIn("# demo", body)

    def test_literal_block_and_quotes(self) -> None:
        fields, _ = _ar.parse_frontmatter('---\nname: "demo"\ndescription: |-\n  one\n  two\n---\nbody\n')
        self.assertEqual(fields, {"name": "demo", "description": "one\ntwo"})

    def test_duplicate_key(self) -> None:
        with self.assertRaises(_ar.FrontmatterError):
            _ar.parse_frontmatter("---\nname: a\nname: b\n---\nbody\n")


class Reconcile(Base):
    def test_changeset_is_empty_with_a_stable_digest(self) -> None:
        empty = hashlib.sha256(json.dumps([], separators=(",", ":")).encode()).hexdigest()
        for repo in (self.repo, make_repo(self.root, "other", aspect=False)):
            result = reconcile_repo(repo)
            self.assertEqual(result["changeset"], [])
            self.assertEqual(result["decisions_required"], [])
            self.assertEqual(result["digest"], empty)


class ThisRepository(unittest.TestCase):
    def test_wamp_ai_aspects_pass(self) -> None:
        wamp_ai = Path(__file__).resolve().parents[1]
        findings = _ar.inspect(wamp_ai)
        self.assertEqual([f for f in findings if f.status != _ar.OK], [])
        self.assertEqual({f.message.split(":")[0] for f in findings}, {"way-a", "aspect-repo"})


if __name__ == "__main__":
    unittest.main()
