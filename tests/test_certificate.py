"""A certificate is a claim a stranger relies on, so the refusals matter more
than the fields. These pin what it will not issue.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (AssayError, Base, Checkpoint, Injection, Pack, Rubric,
                       calibrate, certify, defect_classes, replace_in_reply,
                       run, vac_manifest)

ROOT = Path(__file__).resolve().parents[1]
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


def _pack(defect_text="a wholly different sentence", cls=ROT, n=6):
    bases, injs = [], []
    for i in range(n):
        bid = f"b{i}"
        clean = f"REQUEST: q{i}?\nREPLY: an ordinary answer number {i}."
        bases.append(Base(bid, clean))
        injs.append(Injection(f"break{i}", cls,
                              replace_in_reply(f"an ordinary answer number {i}.",
                                               f"{defect_text} {i}."),
                              applies_to=frozenset({bid})))
    return Pack("p", bases, injs).build()


GOOD = Rubric("r", [Checkpoint("cp", defect_classes(ROT),
                               lambda t: "wholly different" in t, "desc")])


def test_it_refuses_to_certify_against_uncalibrated_material(tmp_path):
    """THE guard. A coverage number from material a coin flip can reach is not
    interpretable, so rating it publishes a figure nobody can read."""
    easy = _pack(defect_text="this reply is rotten", n=4)
    cal = calibrate(easy)
    assert cal.floor > 0
    r = Rubric("r", [Checkpoint("cp", defect_classes(ROT),
                                lambda t: "rotten" in t, "d")])
    with pytest.raises(AssayError, match="nobody can read"):
        certify(tmp_path / "c", r, easy, run(r, easy), cal, repo=_repo(tmp_path))


def test_allow_uncalibrated_puts_the_floor_in_the_claim(tmp_path):
    easy = _pack(defect_text="this reply is rotten", n=4)
    cal = calibrate(easy)
    r = Rubric("r", [Checkpoint("cp", defect_classes(ROT),
                                lambda t: "rotten" in t, "d")])
    p = certify(tmp_path / "c", r, easy, run(r, easy), cal,
                repo=_repo(tmp_path), allow_uncalibrated=True)
    m = json.loads(p.read_text())
    assert "floor" in m["claim"]["capability"]
    assert m["results"]["summary"]["assay"]["floor_pct"] > 0


def test_a_floor_from_other_material_is_refused(tmp_path):
    a, b = _pack(), _pack()
    object.__setattr__(b, "id", "other")
    cal = calibrate(b)
    with pytest.raises(AssayError, match="says nothing about this score"):
        certify(tmp_path / "c", GOOD, a, run(GOOD, a), cal, repo=_repo(tmp_path))


def test_a_dirty_tree_cannot_be_stamped(tmp_path):
    repo = _repo(tmp_path)
    (repo / "dirty.txt").write_text("uncommitted")
    m = _pack()
    with pytest.raises(AssayError, match="dirty tree"):
        certify(tmp_path / "c", GOOD, m, run(GOOD, m), calibrate(m), repo=repo)


def test_porcelain_paths_are_parsed_whole(tmp_path):
    """Regression. _git stripped the whole porcelain output, which ate the
    leading space of an unstaged line and sliced one character off the path,
    producing 'eadcheck/__init__.py'."""
    repo = _repo(tmp_path)
    (repo / "x").write_text("changed")          # unstaged, so the line is ' M x'
    m = _pack()
    with pytest.raises(AssayError) as e:
        certify(tmp_path / "c", GOOD, m, run(GOOD, m), calibrate(m), repo=repo)
    assert ": x" in str(e.value) or " x" in str(e.value)
    assert "M x" not in str(e.value)


def test_reissuing_is_byte_identical(tmp_path):
    """No wall clock anywhere, so a diff means something actually changed."""
    repo, m = _repo(tmp_path), _pack()
    out = tmp_path / "c"
    first = certify(out, GOOD, m, run(GOOD, m), calibrate(m), repo=repo).read_bytes()
    second = certify(out, GOOD, m, run(GOOD, m), calibrate(m), repo=repo).read_bytes()
    assert first == second


def test_the_bundle_is_closed_so_a_later_file_breaks_it(tmp_path):
    repo, m = _repo(tmp_path), _pack()
    out = tmp_path / "c"
    certify(out, GOOD, m, run(GOOD, m), calibrate(m), repo=repo)
    before = {e["path"] for e in json.loads((out / "vac.json").read_text())["evidence"]}
    (out / "smuggled.txt").write_text("rode along")
    after = {e["path"] for e in vac_manifest(out, repo, "x/y")["evidence"]}
    assert "smuggled.txt" in after - before


def test_expect_holds_only_recomputable_fields(tmp_path):
    """Nothing in the headline is the issuer's word."""
    repo, m = _repo(tmp_path), _pack()
    out = tmp_path / "c"
    certify(out, GOOD, m, run(GOOD, m), calibrate(m), repo=repo)
    man = json.loads((out / "vac.json").read_text())
    aj = json.loads((out / "assay.json").read_text())
    exp = man["results"]["checks"][0]["expect"]
    assert exp["classes"] == len(aj["classes"])
    assert exp["covered"] == sum(1 for c in aj["classes"] if c["covered"])
    assert exp["residual"] == len(aj["residual"])
    assert exp["decoration"] == sum(1 for c in aj["checkpoints"] if c["decoration"])


def test_the_scope_is_derived_from_the_artifact_filename(tmp_path):
    """VAC 0.2 binds a summary on <scope>.<field>, and the verifier derives
    scope from the primary evidence filename. Deriving it from the same
    literal here keeps the two from drifting."""
    from deadcheck.certificate import ARTIFACT, SCOPE
    assert SCOPE == ARTIFACT.split(".")[0]
    repo, m = _repo(tmp_path), _pack()
    out = tmp_path / "c"
    certify(out, GOOD, m, run(GOOD, m), calibrate(m), repo=repo)
    man = json.loads((out / "vac.json").read_text())
    assert set(man["results"]["summary"]) == {SCOPE}
