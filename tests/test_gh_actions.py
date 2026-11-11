###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Tests for the gh-actions aspect (wamp-proto/wamp-ai#44).

Workflow files in a temp directory, every state of a ``uses:`` line: pinned, a major
tag, a branch, a short or wrong SHA, a missing or wrong version comment, quoted, not in
the table, local, first-party, docker, malformed; workflows in a subdirectory; deviation
decisions current, stale, malformed and open. The reconcile's ops are applied here with
the semantics of the engine's ``line_replace`` op, and the result is compared byte for
byte. The pins come from this checkout's ``references/actions.toml``, as in a rollout.
``latest.py`` is tested on canned ``git ls-remote`` listings, without the network.
Standard library only: ``python3 -m unittest discover -s tests``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "aspects" / "gh-actions" / "scripts"


def _load(name: str, filename: str):
    """Load one of this aspect's scripts under a name of its own (see test_aspect_repo)."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SCRIPTS))
try:
    _gha = _load("_gha", "_gha.py")
    latest = _load("gh_actions_latest", "latest.py")
    inspect_repo = _load("gh_actions_check", "check.py").inspect_repo
    reconcile_repo = _load("gh_actions_reconcile", "reconcile.py").reconcile_repo
finally:
    sys.path.remove(str(SCRIPTS))

TABLE = _gha.load_table()
CO = TABLE["actions/checkout"]
UV = TABLE["astral-sh/setup-uv"]
CQ = TABLE["github/codeql-action"]


def pinned(action: str, pin: _gha.Pin) -> str:
    return f"{action}@{pin.sha} # {pin.version}"


def apply_ops(repo: Path, ops: list[dict]) -> None:
    """The engine's ``line_replace``: split at \\n, a \\r before it is the ending's."""
    by_path: dict[str, list[dict]] = {}
    for op in ops:
        assert op["action"] == "line_replace", op
        by_path.setdefault(op["path"], []).append(op)
    for rel, file_ops in by_path.items():
        path = repo / rel
        parts = path.read_bytes().decode("utf-8").split("\n")
        for op in file_ops:
            i = op["line"] - 1
            cr = "\r" if parts[i].endswith("\r") else ""
            assert parts[i].removesuffix("\r") == op["old"], (rel, op)
            assert "\n" not in op["new"] and "\r" not in op["new"]
            parts[i] = op["new"] + cr
        path.write_bytes("\n".join(parts).encode("utf-8"))


def statuses(repo: Path) -> list[tuple[str, str]]:
    return [(f.rule, f.status) for f in inspect_repo(repo)]


def fails(repo: Path) -> list[str]:
    return [f.message for f in inspect_repo(repo) if f.status == "FAIL"]


WORKFLOW = """\
name: main
on: [push]
jobs:
  identifiers:
    uses: wamp-proto/wamp-cicd/.github/workflows/identifiers.yml@main
    # uses: ./.cicd/workflows/identifiers.yml
  test:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - name: uv
        uses: astral-sh/setup-uv@v6   # Node 20
      - uses: "actions/checkout@v4"
      - uses: github/codeql-action/init@v4
      - uses: ./.github/actions/local
      - uses: wamp-proto/wamp-cicd/actions/upload-artifact-verified@main
      - run: |
          echo "uses: is just text here"
"""


class Repo(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "member"
        (self.repo / ".github" / "workflows").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, rel: str, text: str) -> Path:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path


class Table(unittest.TestCase):
    def test_the_shipped_table_is_well_formed(self) -> None:
        self.assertGreater(len(TABLE), 10)
        for name, pin in TABLE.items():
            self.assertEqual(name.count("/"), 1, name)
            self.assertRegex(pin.sha, r"^[0-9a-f]{40}$")
            self.assertRegex(pin.version, r"^v\d+\.\d+\.\d+$")

    def test_the_node20_trio_is_past_node20(self) -> None:
        self.assertGreaterEqual(TABLE["actions/checkout"].major, 5)
        self.assertGreaterEqual(TABLE["astral-sh/setup-uv"].major, 7)
        self.assertGreaterEqual(TABLE["extractions/setup-just"].major, 4)

    def test_a_malformed_table_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "actions.toml"
            for text in (
                "",
                '[action."actions/checkout"]\nsha = "abc"\nversion = "v7.0.1"\n',
                f'[action."actions/checkout"]\nsha = "{CO.sha}"\nversion = "v7"\n',
                f'[action."checkout"]\nsha = "{CO.sha}"\nversion = "v7.0.1"\n',
            ):
                bad.write_text(text, encoding="utf-8")
                with self.assertRaises(_gha.TableError, msg=text):
                    _gha.load_table(bad)


class Check(Repo):
    def test_no_workflows_is_ok(self) -> None:
        self.assertEqual(statuses(self.repo), [("pins", "OK")])

    def test_unpinned_lines_fail_one_finding_each(self) -> None:
        self.write(".github/workflows/main.yml", WORKFLOW)
        msgs = fails(self.repo)
        self.assertEqual(len(msgs), 4, msgs)
        self.assertTrue(msgs[0].startswith(".github/workflows/main.yml:10: actions/checkout@v4 - want"))
        self.assertIn("astral-sh/setup-uv@v6 # Node 20", msgs[1])
        self.assertIn(":15: actions/checkout@v4", msgs[2])
        self.assertIn("github/codeql-action/init@v4", msgs[3])

    def test_pinned_lines_pass(self) -> None:
        self.write(
            ".github/workflows/main.yml",
            f"jobs:\n  t:\n    steps:\n      - uses: {pinned('actions/checkout', CO)}\n"
            f"        uses: {pinned('github/codeql-action/analyze', CQ)}\n",
        )
        self.assertEqual(fails(self.repo), [])
        self.assertIn(("pins", "OK"), statuses(self.repo))

    def test_every_kind_of_divergence_fails(self) -> None:
        good = pinned("actions/checkout", CO)
        for line in (
            "actions/checkout@v7",  # major tag
            "actions/checkout@v7.0.1",  # exact tag
            "actions/checkout@main",  # branch
            f"actions/checkout@{CO.sha[:7]} # {CO.version}",  # short sha
            f"actions/checkout@{CO.sha}",  # no version comment
            f"actions/checkout@{CO.sha} # v7.0.0",  # wrong version comment
            f"actions/checkout@{CO.sha}  # {CO.version}",  # two blanks
            f'"{good}"'.replace(" # ", '" # ').removesuffix('"'),  # quoted value
            f"actions/checkout@{'1' * 40} # {CO.version}",  # other commit
        ):
            with self.subTest(line=line):
                self.write(".github/workflows/w.yml", f"steps:\n  - uses: {line}\n")
                self.assertEqual(len(fails(self.repo)), 1, line)

    def test_an_action_not_in_the_table_fails_without_an_op(self) -> None:
        self.write(".github/workflows/w.yml", "steps:\n  - uses: someone/new-action@v1\n")
        self.assertEqual(fails(self.repo), [".github/workflows/w.yml:2: someone/new-action is not in the pin table"])
        self.assertEqual(reconcile_repo(self.repo)["changeset"], [])

    def test_local_first_party_and_comments_are_skipped(self) -> None:
        self.write(
            ".github/workflows/w.yml",
            "jobs:\n  a:\n    uses: ./.github/workflows/x.yml\n"
            "    # uses: actions/checkout@v4\n"
            "  b:\n    uses: wamp-proto/wamp-cicd/.github/workflows/identifiers.yml@main\n",
        )
        self.assertEqual(fails(self.repo), [])

    def test_docker_is_a_warning(self) -> None:
        self.write(".github/workflows/w.yml", "steps:\n  - uses: docker://alpine:3.20\n")
        self.assertIn(("pins", "WARN"), statuses(self.repo))
        self.assertEqual(fails(self.repo), [])

    def test_a_malformed_value_fails(self) -> None:
        self.write(".github/workflows/w.yml", "steps:\n  - uses: actions/checkout\n")
        self.assertEqual(len(fails(self.repo)), 1)

    def test_workflows_in_subdirectories_are_dead_files(self) -> None:
        self.write(".github/workflows/.old/deploy.yml", "steps:\n  - uses: actions/checkout@v2\n")
        self.assertEqual(fails(self.repo), [])
        self.assertIn(("dead-files", "WARN"), statuses(self.repo))
        self.assertEqual(reconcile_repo(self.repo)["changeset"], [])

    def test_local_composite_actions_are_checked(self) -> None:
        self.write(".github/actions/setup/action.yml", "runs:\n  steps:\n    - uses: astral-sh/setup-uv@v6\n")
        self.assertEqual(len(fails(self.repo)), 1)
        ops = reconcile_repo(self.repo)["changeset"]
        self.assertEqual([op["path"] for op in ops], [".github/actions/setup/action.yml"])

    def test_yaml_extension_is_read(self) -> None:
        self.write(".github/workflows/w.yaml", "steps:\n  - uses: actions/checkout@v4\n")
        self.assertEqual(len(fails(self.repo)), 1)


class Reconcile(Repo):
    def test_reconcile_makes_the_check_pass_and_changes_nothing_else(self) -> None:
        path = self.write(".github/workflows/main.yml", WORKFLOW)
        r = reconcile_repo(self.repo)
        self.assertTrue(r["applicable"])
        self.assertEqual([op["line"] for op in r["changeset"]], [10, 14, 15, 16])
        apply_ops(self.repo, r["changeset"])
        self.assertEqual(fails(self.repo), [])
        after = path.read_text(encoding="utf-8").split("\n")
        before = WORKFLOW.split("\n")
        changed = [i + 1 for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
        self.assertEqual(changed, [10, 14, 15, 16])
        self.assertEqual(after[9], f"      - uses: {pinned('actions/checkout', CO)}")
        self.assertEqual(after[13], f"        uses: {pinned('astral-sh/setup-uv', UV)}")
        self.assertEqual(after[14], f"      - uses: {pinned('actions/checkout', CO)}")
        self.assertEqual(after[15], f"      - uses: {pinned('github/codeql-action/init', CQ)}")

    def test_reconcile_on_a_pinned_tree_is_empty(self) -> None:
        self.write(".github/workflows/main.yml", WORKFLOW)
        apply_ops(self.repo, reconcile_repo(self.repo)["changeset"])
        again = reconcile_repo(self.repo)
        self.assertEqual(again["changeset"], [])

    def test_crlf_and_no_final_newline_are_kept(self) -> None:
        text = "steps:\r\n  - uses: actions/checkout@v4\r\n  - uses: astral-sh/setup-uv@v6"
        path = self.write(".github/workflows/w.yml", text)
        apply_ops(self.repo, reconcile_repo(self.repo)["changeset"])
        want = (
            f"steps:\r\n  - uses: {pinned('actions/checkout', CO)}\r\n"
            f"  - uses: {pinned('astral-sh/setup-uv', UV)}"
        )
        self.assertEqual(path.read_bytes(), want.encode("utf-8"))
        self.assertEqual(fails(self.repo), [])

    def test_output_is_deterministic(self) -> None:
        self.write(".github/workflows/b.yml", WORKFLOW)
        self.write(".github/workflows/a.yml", WORKFLOW)
        out = [
            subprocess.run(
                [sys.executable, str(SCRIPTS / "reconcile.py"), "--json", str(self.repo)],
                capture_output=True, text=True, check=True,
            ).stdout
            for _ in range(2)
        ]
        self.assertEqual(out[0], out[1])
        ops = reconcile_repo(self.repo)["changeset"]
        self.assertEqual(ops, sorted(ops, key=lambda op: (op["path"], op["line"])))
        self.assertEqual(ops[0]["path"], ".github/workflows/a.yml")

    def test_no_workflows_is_not_applicable(self) -> None:
        r = reconcile_repo(self.repo)
        self.assertFalse(r["applicable"])
        self.assertEqual(r["changeset"], [])


class Decisions(Repo):
    OLD = _gha.Pin("49933ea5288caeca8642d1e84afbd3f7d6820020", "v4.4.0")

    def decision(self, name: str = "20261111-gh_actions_deviation.toml", *, answer: str = "keep",
                 sha256: str | None = None, extra: str = "") -> None:
        if sha256 is None:
            sha256 = _gha.canonical_sha256(_gha.table_observation(TABLE, ["actions/checkout"]))
        self.write(
            f".decisions/gh-actions/{name}",
            'schema = 1\naspect = "gh-actions"\ntype = "gh_actions_deviation"\n'
            'question = "Keep actions/checkout at v4.4.0?"\noptions = ["keep", "follow"]\n'
            f'answer = "{answer}"\ndecided_by = "human"\n{extra}\n'
            f'[[keep]]\naction = "actions/checkout"\nsha = "{self.OLD.sha}"\nversion = "{self.OLD.version}"\n'
            'reason = "test"\n\n'
            f'[precondition]\npaths = ["actions.toml#actions/checkout"]\nsha256 = "{sha256}"\n',
        )

    def setUp(self) -> None:
        super().setUp()
        self.write(".github/workflows/w.yml", f"steps:\n  - uses: {pinned('actions/checkout', self.OLD)}\n")

    def test_without_a_decision_the_old_pin_fails(self) -> None:
        self.assertEqual(len(fails(self.repo)), 1)

    def test_a_current_keep_decision_passes(self) -> None:
        self.decision()
        self.assertEqual(fails(self.repo), [])
        self.assertIn(("decisions", "OK"), statuses(self.repo))
        self.assertEqual(reconcile_repo(self.repo)["changeset"], [])

    def test_a_kept_action_is_reconciled_to_the_kept_pin(self) -> None:
        self.decision()
        self.write(".github/workflows/w.yml", "steps:\n  - uses: actions/checkout@v4\n")
        ops = reconcile_repo(self.repo)["changeset"]
        self.assertEqual([op["new"] for op in ops], [f"  - uses: {pinned('actions/checkout', self.OLD)}"])

    def test_follow_ends_the_deviation(self) -> None:
        self.decision(answer="follow")
        self.assertEqual(len(fails(self.repo)), 1)

    def test_a_stale_decision_fails(self) -> None:
        self.decision(sha256="0" * 64)
        msgs = fails(self.repo)
        self.assertTrue(any("decide again" in m for m in msgs), msgs)

    def test_a_malformed_decision_fails(self) -> None:
        self.write(".decisions/gh-actions/20261111-gh_actions_deviation.toml", 'schema = 1\naspect = "gh-actions"\n')
        self.assertTrue(any("gh_actions_deviation.toml" in m for m in fails(self.repo)))

    def test_newest_wins_and_must_name_its_predecessor(self) -> None:
        self.decision()
        self.decision("20261112-gh_actions_deviation.toml", answer="follow")
        self.assertTrue(any("supersedes" in m for m in fails(self.repo)))
        self.decision("20261112-gh_actions_deviation.toml", answer="follow",
                      extra='supersedes = "20261111-gh_actions_deviation.toml"')
        msgs = fails(self.repo)
        self.assertEqual(len(msgs), 1, msgs)  # follow: the old pin fails again
        self.assertIn("want", msgs[0])

    def test_an_open_decision_fails_and_stops_the_reconcile(self) -> None:
        self.write(".decisions/gh-actions/OPEN-20261111-gh_actions_deviation.toml", 'question = "?"\n')
        self.write(".github/workflows/x.yml", "steps:\n  - uses: actions/checkout@v4\n")
        self.assertIn(("open-decisions", "FAIL"), statuses(self.repo))
        r = reconcile_repo(self.repo)
        self.assertEqual(r["changeset"], [])
        self.assertEqual(r["decisions_required"], [".decisions/gh-actions/OPEN-20261111-gh_actions_deviation.toml"])


class ThisRepository(unittest.TestCase):
    def test_wamp_ai_own_workflows_are_pinned(self) -> None:
        wamp_ai = Path(__file__).resolve().parents[1]
        self.assertTrue((wamp_ai / ".github" / "workflows" / "gh-actions-latest.yml").is_file())
        self.assertEqual(fails(wamp_ai), [])


LISTING = """\
1111111111111111111111111111111111111111\trefs/tags/v4
2222222222222222222222222222222222222222\trefs/tags/v4.2.2
3333333333333333333333333333333333333333\trefs/tags/v4.3.0
aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/tags/v5.0.0
bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/tags/v5.0.0^{}
cccccccccccccccccccccccccccccccccccccccc\trefs/tags/v6.0.0-beta.1
dddddddddddddddddddddddddddddddddddddddd\trefs/tags/codeql-bundle-v9.9.9
"""


class Latest(unittest.TestCase):
    def test_releases_peel_annotated_tags_and_skip_other_shapes(self) -> None:
        rel = latest.releases(LISTING)
        self.assertEqual(sorted(rel), [(4, 2, 2), (4, 3, 0), (5, 0, 0)])
        self.assertEqual(rel[(5, 0, 0)].sha, "b" * 40)

    def test_current(self) -> None:
        row = latest.compare("o/r", _gha.Pin("b" * 40, "v5.0.0"), LISTING)
        self.assertEqual(row.status, "current")
        self.assertFalse(row.behind)

    def test_minor_behind(self) -> None:
        listing = LISTING.replace("refs/tags/v5", "refs/tags/v0")
        row = latest.compare("o/r", _gha.Pin("2" * 40, "v4.2.2"), listing)
        self.assertEqual((row.status, row.in_major), ("minor behind", "v4.3.0"))

    def test_major_behind(self) -> None:
        row = latest.compare("o/r", _gha.Pin("3" * 40, "v4.3.0"), LISTING)
        self.assertEqual((row.status, row.newest, row.newest_sha), ("major behind", "v5.0.0", "b" * 40))

    def test_a_pin_that_is_not_the_release_commit(self) -> None:
        row = latest.compare("o/r", _gha.Pin("9" * 40, "v4.3.0"), LISTING)
        self.assertEqual(row.status, "pin not a release")

    def test_report_and_markdown(self) -> None:
        rows = latest.report(lambda action: LISTING)
        self.assertEqual(len(rows), len(TABLE))
        md = latest.markdown(rows)
        self.assertIn("| action | pinned |", md)
        self.assertIn('sha     = "' + "b" * 40 + '"', md)


if __name__ == "__main__":
    unittest.main()
