###############################################################################
#
#  Copyright (C) typedef int GmbH
#  SPDX-License-Identifier: MIT
#
###############################################################################
"""Tests for the fleet-repo aspect, rules 1 and 2 (wamp-proto/wamp-ai#40).

A fixture fleet repository in a temp directory: one converged record and its index,
in the rollout engine's format. Then one fixture per check that breaks exactly one
thing: that check FAILs, and nothing else. Standard library only:
``python3 -m unittest discover -s tests``.
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

SCRIPTS = Path(__file__).resolve().parents[1] / "aspects" / "fleet-repo" / "scripts"


def _load(name: str, filename: str):
    """Load one of this aspect's scripts under a name of its own (see test_aspect_repo)."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SCRIPTS))
try:
    _fr = _load("_fr", "_fr.py")
    check = _load("fleet_repo_check", "check.py")
    reconcile_repo = _load("fleet_repo_reconcile", "reconcile.py").reconcile_repo
finally:
    sys.path.remove(str(SCRIPTS))

A, B, C, D, E = ("a" * 40, "b" * 40, "c" * 40, "d" * 40, "e" * 40)
CHANGESET = '[{"action":"submodule_pin","path":".ai","rev":"' + A + '"}]'
EMPTY = hashlib.sha256(b"[]").hexdigest()

MEMBER = {
    "repo": "target",
    "slug": "org/target",
    "issue": 7,
    "base": A,
    "commit": B,
    "merge": C,
    "provider_pin": D,
    "proof_provider_rev": D,
    "proof_rev": C,
    "proof_changeset_sha256": EMPTY,
    "changes": ["aspects.toml", ".ai"],
    "changeset_sha256": hashlib.sha256(CHANGESET.encode()).hexdigest(),
    "changeset": CHANGESET,
}

HEADER = """<!-- Generated at each rollout close-out, from the rollout.toml records in this
     directory. Do not edit: it is rewritten. -->

# Rollouts

| rollout | aspect | status | fleet issue | members | changes | aspect rev |
|---|---|---|---|---|---|---|
"""


def _v(value) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(v) for v in value) + "]"
    return str(value)


def record_toml(rid: str, aspect: str = "way-a", status: str = "converged", fleet: str = "org/fleet",
                fleet_issue: int | None = 3, schema: int = 1, members: list[dict] | None = None) -> str:
    out = [f"schema = {schema}", f"id = {_v(rid)}", f"aspect = {_v(aspect)}", f"status = {_v(status)}",
           f"fleet = {_v(fleet)}"]
    if fleet_issue is not None:
        out.append(f"fleet_issue = {fleet_issue}")
    out += ["", "[provider]", 'repo = "org/provider"', f"rev = {_v(D)}", "", "[apex]", f"rev = {_v(E)}"]
    for m in members if members is not None else [dict(MEMBER)]:
        out += ["", "[[member]]"]
        decisions = m.pop("decision", [])
        out += [f"{k} = {_v(v)}" for k, v in m.items()]
        for d in decisions:
            out += ["", "[[member.decision]]"] + [f"{k} = {_v(v)}" for k, v in d.items()]
    return "\n".join(out) + "\n"


def index_row(rid: str, aspect: str = "way-a", status: str = "converged", issue: int | None = 3,
              link: str | None = None) -> str:
    cell = "-" if issue is None else f"[#{issue}](https://github.com/org/fleet/issues/{issue})"
    return (f"| [`{rid}`]({link or rid}/rollout.toml) | `{aspect}` | {status} | {cell} | "
            f"[target#7](https://github.com/org/target/issues/7) | `.ai`, `aspects.toml` | `{D[:9]}` |\n")


def make_fleet(root: Path, dirname: str = "fleet", remote: str | None = None) -> Path:
    repo = root / dirname
    (repo / "rollouts").mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True, capture_output=True)
    if remote:
        subprocess.run(["git", "-C", str(repo), "remote", "add", "upstream", remote], check=True, capture_output=True)
    return repo


def fails(repo: Path) -> list[str]:
    return sorted({f.rule for f in _fr.inspect(repo) if f.status == _fr.FAIL})


class Base(unittest.TestCase):
    RID = "20261010-way-a"

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = make_fleet(self.root)
        self.write_record(self.RID, record_toml(self.RID))
        self.write_index([index_row(self.RID)])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_record(self, rid: str, text: str) -> None:
        folder = self.repo / "rollouts" / rid
        folder.mkdir(exist_ok=True)
        (folder / "rollout.toml").write_text(text, encoding="utf-8")

    def write_index(self, rows: list[str], header: str = HEADER) -> None:
        (self.repo / "rollouts" / "README.md").write_text(header + "".join(rows), encoding="utf-8")

    def member(self, **changes) -> list[dict]:
        m = dict(MEMBER)
        for k, v in changes.items():
            if v is None:
                m.pop(k, None)
            else:
                m[k] = v
        return [m]


class Conforming(Base):
    def test_conforming_fleet_has_only_ok(self) -> None:
        findings = _fr.inspect(self.repo)
        self.assertEqual([f for f in findings if f.status != _fr.OK], [])
        self.assertEqual({f.rule for f in findings}, {"record", "index"})

    def test_check_main_exits_zero(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(check.main([str(self.repo)]), 0)

    def test_no_fleet_issue_is_a_dash_in_the_index(self) -> None:
        self.write_record(self.RID, record_toml(self.RID, fleet_issue=None))
        self.write_index([index_row(self.RID, issue=None)])
        self.assertEqual(fails(self.repo), [])

    def test_a_stop_commit_stands_in_for_commit_at_executed(self) -> None:
        members = self.member(commit=None, merge=None, proof_rev=None, proof_changeset_sha256=None, stop_commit=E)
        self.write_record(self.RID, record_toml(self.RID, status="executed", members=members))
        self.write_index([index_row(self.RID, status="executed")])
        self.assertEqual(fails(self.repo), [])


class RecordChecks(Base):
    """Rule 1: each fixture breaks exactly one thing; exactly that check FAILs."""

    def test_1_schema_unknown(self) -> None:
        self.write_record(self.RID, record_toml(self.RID, schema=2))
        self.assertEqual(fails(self.repo), ["schema"])

    def test_1_does_not_parse(self) -> None:
        self.write_record(self.RID, "schema = \n")
        self.assertEqual(fails(self.repo), ["schema"])

    def test_2_id_not_the_folder(self) -> None:
        self.write_record(self.RID, record_toml("20261011-way-a"))
        self.assertEqual(fails(self.repo), ["id"])

    def test_2_id_names_another_aspect(self) -> None:
        self.write_record(self.RID, record_toml(self.RID, aspect="python-package"))
        self.write_index([index_row(self.RID, aspect="python-package")])
        self.assertEqual(fails(self.repo), ["id"])

    def test_3_unknown_status(self) -> None:
        self.write_record(self.RID, record_toml(self.RID, status="done"))
        self.write_index([index_row(self.RID, status="done")])
        self.assertEqual(fails(self.repo), ["status"])

    def test_4_fleet_names_another_repository(self) -> None:
        self.write_record(self.RID, record_toml(self.RID, fleet="org/other-fleet"))
        self.assertEqual(fails(self.repo), ["fleet"])

    def test_5_short_sha(self) -> None:
        self.write_record(self.RID, record_toml(self.RID, members=self.member(merge=C[:7])))
        self.assertEqual(fails(self.repo), ["revs"])

    def test_5_decision_commit_short(self) -> None:
        members = self.member(decision=[{"commit": "abc", "type": "t", "decided_by": "human",
                                         "precondition_sha256": EMPTY}])
        self.write_record(self.RID, record_toml(self.RID, members=members))
        self.assertEqual(fails(self.repo), ["revs"])

    def test_6_member_without_changeset_sha256(self) -> None:
        self.write_record(self.RID, record_toml(self.RID, members=self.member(changeset_sha256=None)))
        self.assertEqual(fails(self.repo), ["members"])

    def test_6_changeset_edited_after_its_hash(self) -> None:
        self.write_record(self.RID, record_toml(self.RID, members=self.member(changeset=CHANGESET.replace(".ai", ".cicd"))))
        self.assertEqual(fails(self.repo), ["members"])

    def test_7_converged_without_proof_of_an_empty_changeset(self) -> None:
        self.write_record(self.RID, record_toml(self.RID, members=self.member(proof_changeset_sha256="f" * 64)))
        self.assertEqual(fails(self.repo), ["promises"])

    def test_7_executed_with_neither_commit_nor_stop_commit(self) -> None:
        members = self.member(commit=None, merge=None, proof_rev=None, proof_changeset_sha256=None)
        self.write_record(self.RID, record_toml(self.RID, status="executed", members=members))
        self.write_index([index_row(self.RID, status="executed")])
        self.assertEqual(fails(self.repo), ["promises"])

    def test_7_issues_filed_without_issue(self) -> None:
        members = self.member(issue=None, commit=None, merge=None, proof_rev=None, proof_changeset_sha256=None)
        self.write_record(self.RID, record_toml(self.RID, status="issues-filed", members=members))
        self.write_index([index_row(self.RID, status="issues-filed")])
        self.assertEqual(fails(self.repo), ["promises"])

    def test_7_landed_without_merge(self) -> None:
        members = self.member(merge=None, proof_rev=None, proof_changeset_sha256=None)
        self.write_record(self.RID, record_toml(self.RID, status="landed", members=members))
        self.write_index([index_row(self.RID, status="landed")])
        self.assertEqual(fails(self.repo), ["promises"])

    def test_8_unknown_decider(self) -> None:
        members = self.member(decision=[{"commit": E, "type": "t", "decided_by": "robot",
                                         "precondition_sha256": EMPTY}])
        self.write_record(self.RID, record_toml(self.RID, members=members))
        self.assertEqual(fails(self.repo), ["decisions"])


class IndexChecks(Base):
    """Rule 2: each fixture breaks exactly one thing; exactly that check FAILs."""

    OLDER = "20261008-way-a"

    def test_1_no_index(self) -> None:
        (self.repo / "rollouts" / "README.md").unlink()
        self.assertEqual(fails(self.repo), ["index-header"])

    def test_1_index_without_its_generated_comment(self) -> None:
        self.write_index([index_row(self.RID)], header=HEADER.split("\n", 2)[2])
        self.assertEqual(fails(self.repo), ["index-header"])

    def test_2_record_missing_from_the_index(self) -> None:
        self.write_record(self.OLDER, record_toml(self.OLDER))
        self.assertEqual(fails(self.repo), ["index-set"])

    def test_2_row_without_a_record(self) -> None:
        self.write_index([index_row(self.RID), index_row(self.OLDER)])
        self.assertEqual(fails(self.repo), ["index-set"])

    def test_2_row_listed_twice(self) -> None:
        self.write_index([index_row(self.RID), index_row(self.RID)])
        self.assertEqual(fails(self.repo), ["index-set"])

    def test_3_wrong_aspect_in_a_row(self) -> None:
        self.write_index([index_row(self.RID, aspect="python-package")])
        self.assertEqual(fails(self.repo), ["index-rows"])

    def test_3_stale_status_in_a_row(self) -> None:
        self.write_index([index_row(self.RID, status="executed")])
        self.assertEqual(fails(self.repo), ["index-rows"])

    def test_3_wrong_fleet_issue_in_a_row(self) -> None:
        self.write_index([index_row(self.RID, issue=4)])
        self.assertEqual(fails(self.repo), ["index-rows"])

    def test_3_link_to_another_folder(self) -> None:
        self.write_index([index_row(self.RID, link=self.OLDER)])
        self.assertEqual(fails(self.repo), ["index-rows"])

    def test_4_rows_out_of_order(self) -> None:
        self.write_record(self.OLDER, record_toml(self.OLDER))
        self.write_index([index_row(self.OLDER), index_row(self.RID)])
        self.assertEqual(fails(self.repo), ["index-order"])

    def test_two_records_newest_first_pass(self) -> None:
        self.write_record(self.OLDER, record_toml(self.OLDER))
        self.write_index([index_row(self.RID), index_row(self.OLDER)])
        self.assertEqual(fails(self.repo), [])


class FleetName(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _fleet(self, dirname: str, remote: str | None, fleet: str) -> Path:
        repo = make_fleet(self.root, dirname, remote)
        rid = "20261010-way-a"
        (repo / "rollouts" / rid).mkdir()
        (repo / "rollouts" / rid / "rollout.toml").write_text(record_toml(rid, fleet=fleet), encoding="utf-8")
        (repo / "rollouts" / "README.md").write_text(HEADER + index_row(rid), encoding="utf-8")
        return repo

    def test_github_remote_full_slug(self) -> None:
        repo = self._fleet("fleet-owner", "git@github.com:org/fleet.git", "org/fleet")
        self.assertEqual(fails(repo), [])

    def test_github_remote_other_org_fails(self) -> None:
        repo = self._fleet("fleet", "https://github.com/org/fleet.git", "otherorg/fleet")
        self.assertEqual(fails(repo), ["fleet"])

    def test_no_github_remote_compares_the_name_with_the_directory(self) -> None:
        self.assertEqual(fails(self._fleet("fleet", None, "anyorg/fleet")), [])
        self.assertEqual(fails(self._fleet("fleet-owner", None, "org/fleet")), ["fleet"])


class NoRollouts(unittest.TestCase):
    def test_no_rollout_is_one_warn_and_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_fleet(Path(tmp))
            findings = _fr.inspect(repo)
            self.assertEqual([(f.rule, f.status) for f in findings], [("rollouts-present", _fr.WARN)])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(check.main([str(repo)]), 0)


class Reconcile(Base):
    def test_changeset_is_empty_with_a_stable_digest(self) -> None:
        empty = hashlib.sha256(json.dumps([], separators=(",", ":")).encode()).hexdigest()
        result = reconcile_repo(self.repo)
        self.assertEqual((result["changeset"], result["decisions_required"], result["digest"]), ([], [], empty))


if __name__ == "__main__":
    unittest.main()
