"""The command every certificate's replay block names. It existed in the
instructions for nine commits before it existed in the package, which is the
failure this whole repo is about: an unrunnable check reads like a passing one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (Base, Checkpoint, Injection, Pack, Rubric, calibrate,
                       certify, defect_classes, replace_in_reply, run)
from deadcheck.recompute import check, main, recompute

ROT = "rot"


def _repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    for c in (["init", "-q"], ["config", "user.email", "t@t"],
              ["config", "user.name", "t"]):
        subprocess.run(["git", *c], cwd=r, check=True, capture_output=True)
    (r / "x").write_text("x")
    subprocess.run(["git", "add", "x"], cwd=r, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=r, check=True,
                   capture_output=True)
    return r


def _issue(tmp_path):
    repo = _repo(tmp_path)
    bases, injs = [], []
    for i in range(6):
        bid = f"b{i}"
        bases.append(Base(bid, f"REQUEST: q{i}?\nREPLY: an ordinary answer {i}."))
        injs.append(Injection(f"br{i}", ROT,
                              replace_in_reply(f"an ordinary answer {i}.",
                                               f"a wholly different line {i}."),
                              applies_to=frozenset({bid})))
    m = Pack("p", bases, injs).build()
    r = Rubric("r", [Checkpoint("cp", defect_classes(ROT),
                                lambda t: "wholly different" in t, "d")])
    root = repo / "certs"
    d = root / "r"
    certify(d, r, m, run(r, m), calibrate(m), repo=repo, cert_root=root)
    return d


def _edit(d, fn):
    aj = json.loads((d / "assay.json").read_text())
    fn(aj)
    (d / "assay.json").write_text(json.dumps(aj, indent=1, sort_keys=True) + "\n")
    return aj


def test_the_command_the_certificate_names_actually_exists(tmp_path):
    """Regression for the original defect: every emitted bundle told verifiers
    to run `python -m deadcheck.recompute`, and the module did not exist."""
    d = _issue(tmp_path)
    assert main([str(d)]) == 0


def test_an_honest_bundle_is_consistent(tmp_path):
    code, report = check(_issue(tmp_path))
    assert code == 0
    assert "consistent" in report
    assert "not an independent re-run" in report   # the limit is stated


def test_a_doctored_separation_is_caught_against_the_raw_counts(tmp_path):
    d = _issue(tmp_path)
    _edit(d, lambda aj: aj["checkpoints"][0].__setitem__("separation", 0.99))
    code, report = check(d)
    assert code == 1
    assert "counts give" in report


def test_a_residual_that_does_not_match_the_covered_flags_is_caught(tmp_path):
    d = _issue(tmp_path)
    _edit(d, lambda aj: aj.__setitem__("residual", ["ghost"]))
    code, report = check(d)
    assert code == 1 and "covered flags give" in report


def test_a_mislabelled_decoration_flag_is_caught(tmp_path):
    d = _issue(tmp_path)
    _edit(d, lambda aj: aj["checkpoints"][0].__setitem__("decoration", True))
    assert "implies" in check(d)[1]


def test_a_floor_that_is_not_the_best_probe_is_caught(tmp_path):
    d = _issue(tmp_path)
    _edit(d, lambda aj: aj["calibration"].__setitem__("floor", 0.5))
    report = check(d)[1]
    assert "best probe gives" in report
    assert "difficulty" in report      # 1 - floor no longer holds either


def test_a_class_covered_by_nobody_is_caught(tmp_path):
    d = _issue(tmp_path)

    def tamper(aj):
        aj["classes"][0]["covering_checkpoints"] = []
    _edit(d, tamper)
    assert "no covering checkpoint named" in check(d)[1]


def test_a_missing_artifact_exits_two_not_zero(tmp_path):
    d = _issue(tmp_path)
    (d / "assay.json").unlink()
    code, report = check(d)
    assert code == 2 and "no " in report


def test_no_arguments_does_not_report_success():
    """Exiting 0 on an empty invocation would make a misconfigured CI step
    read as a passing verification."""
    assert main([]) == 2
