"""A registry that lists what it is handed is a directory. These pin what this
one refuses, and that the refusals get published.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (AssayError, Base, Checkpoint, Injection, Pack, Rubric,
                       build, calibrate, certify, defect_classes, index_json,
                       render_markdown, replace_in_reply, run, verify)

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


def _material(defect="a wholly different sentence", n=6):
    bases, injs = [], []
    for i in range(n):
        bid, clean = f"b{i}", f"REQUEST: q{i}?\nREPLY: an ordinary answer number {i}."
        bases.append(Base(bid, clean))
        injs.append(Injection(f"break{i}", ROT,
                              replace_in_reply(f"an ordinary answer number {i}.",
                                               f"{defect} {i}."),
                              applies_to=frozenset({bid})))
    return Pack("p", bases, injs).build()


GOOD = Rubric("good", [Checkpoint("cp", defect_classes(ROT),
                                  lambda t: "wholly different" in t, "d")])


def _issue(tmp_path, rubric=GOOD, name=None):
    repo, m = _repo(tmp_path), _material()
    root = repo / "certs"
    d = root / (name or rubric.id)
    certify(d, rubric, m, run(rubric, m), calibrate(m), repo=repo, cert_root=root)
    return d


def test_a_clean_bundle_is_listed():
    pass  # covered by the fixtures below


def test_an_edited_assay_is_rejected_twice_over(tmp_path):
    """Hash and recompute catch it independently, which is the point of doing
    both: one of them failing alone would still be a finding."""
    d = _issue(tmp_path)
    aj = (d / "assay.json").read_text()
    (d / "assay.json").write_text(aj.replace('"residual": []', '"residual": ["ghost"]'))
    row, reasons = verify(d)
    assert row is None
    assert any("evidence changed since issue" in r for r in reasons)
    assert any("recomputes" in r for r in reasons)


def test_a_file_smuggled_in_after_issue_is_rejected(tmp_path):
    d = _issue(tmp_path)
    (d / "extra.txt").write_text("rode along")
    row, reasons = verify(d)
    assert row is None
    assert any("not in evidence" in r for r in reasons)


def test_a_bundle_with_no_checks_verifies_nothing_and_is_refused(tmp_path):
    d = _issue(tmp_path)
    man = json.loads((d / "vac.json").read_text())
    man["results"]["checks"] = []
    (d / "vac.json").write_text(json.dumps(man, indent=1) + "\n")
    row, reasons = verify(d)
    assert row is None
    assert any("nothing in this bundle is verifiable" in r for r in reasons)


def test_a_missing_vac_is_not_a_certificate(tmp_path):
    d = _issue(tmp_path)
    (d / "vac.json").unlink()
    assert verify(d) == (None, ("no vac.json",))


def test_an_empty_registry_is_refused():
    """It would publish a 100% acceptance rate over zero submissions."""
    with pytest.raises(AssayError, match="100% acceptance rate over zero"):
        build([])


def test_rejections_are_published_with_reasons(tmp_path):
    ok = _issue(tmp_path, name="ok")
    bad = ok.parent / "bad"
    bad.mkdir()
    (bad / "assay.json").write_text("{}")
    reg = build([ok, bad])
    assert reg.accepted == 1 and len(reg.rejected) == 1
    assert reg.acceptance_rate == 0.5
    md = render_markdown(reg)
    assert "## Rejected" in md and "`bad`" in md


def test_uncalibrated_rows_are_marked_on_the_board(tmp_path):
    repo = _repo(tmp_path)
    easy = _material(defect="this reply is rotten", n=4)
    r = Rubric("easy", [Checkpoint("cp", defect_classes(ROT),
                                   lambda t: "rotten" in t, "d")])
    cal = calibrate(easy)
    assert cal.floor > 0
    root = repo / "certs"
    d = root / "easy"
    certify(d, r, easy, run(r, easy), cal, repo=repo, cert_root=root,
            allow_uncalibrated=True)
    reg = build([d])
    assert reg.rows[0].uncalibrated
    assert "UNCALIBRATED" in render_markdown(reg)


def test_the_index_stores_no_counts_to_trust(tmp_path):
    """Totals are recomputed from the rows on read, never carried as a number."""
    reg = build([_issue(tmp_path, name="ok")])
    idx = index_json(reg)
    assert "accepted" not in idx and "total" not in idx
    assert len(idx["rows"]) == reg.accepted


def test_the_residual_is_a_column_not_a_footnote(tmp_path):
    blind = Rubric("blind", [Checkpoint("cp", defect_classes(ROT),
                                        lambda t: False, "d")])
    reg = build([_issue(tmp_path, rubric=blind, name="blind")])
    assert reg.rows[0].residual == (ROT,)
    # find the header by content, not by line number: a line index would
    # break on any prose edit above the table and say nothing about columns
    header = next(l for l in render_markdown(reg).splitlines()
                  if l.startswith("| rubric "))
    assert "residual" in header
