"""Five defects that 114 passing tests sat on top of.

None was found by reading. Each was found by constructing an input designed to
make a layer lie and checking whether it did. These pin that behaviour so the
suite can go red for it from now on.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (AssayError, Base, Checkpoint, Evasion, Injection, Pack,
                       Rating, Rubric, Specimen, SpecimenSet, agree, attack,
                       defect_classes, power, replace_in_reply, run, verify)

R = "rot"


def test_specimens_refuse_two_specimens_with_identical_bytes():
    """An injection on b1 can land exactly on b2's clean text. The per-base
    no-op check cannot see that, and the result is a defective specimen
    byte-identical to a clean one: contradictory ground truth."""
    b1 = Base("b1", "REQUEST: q?\nREPLY: alpha.")
    b2 = Base("b2", "REQUEST: q?\nREPLY: beta.")
    inj = Injection("x", R, replace_in_reply("alpha.", "beta."),
                    applies_to=frozenset({"b1"}))
    with pytest.raises(AssayError, match="byte-identical"):
        Pack("p", [b1, b2], [inj]).build()


def test_registry_refuses_evidence_that_escapes_the_bundle(tmp_path):
    """'Closed evidence' means closed. A manifest vouching for bytes outside
    its own directory can have them swapped without touching the bundle."""
    d = tmp_path / "cert"
    d.mkdir()
    secret = tmp_path / "outside.txt"
    secret.write_text("x")
    (d / "assay.json").write_text(json.dumps({
        "rubric_id": "r", "specimen_set_id": "s", "material_sha": "x",
        "classes": [], "checkpoints": [], "residual": [],
        "calibration": {"floor": 0, "difficulty": 1, "best_probe": "coin",
                        "cheap_classes": [], "probes": []}}))
    man = {"vac_version": "0.2",
           "evidence": [
               {"path": "../outside.txt",
                "sha256": hashlib.sha256(b"x").hexdigest()},
               {"path": "assay.json",
                "sha256": hashlib.sha256((d / "assay.json").read_bytes()).hexdigest()}],
           "results": {"summary": {"assay": {}},
                       "checks": [{"expect": {"classes": 0}}]}}
    (d / "vac.json").write_text(json.dumps(man))
    row, reasons = verify(d)
    assert row is None
    assert any("escapes the bundle" in r for r in reasons)


def test_adversary_does_not_count_a_repair_as_an_evasion():
    """A mutation that lands on a specimen the material labels CLEAN deleted
    the defect. Declared preservation does not override the pack's own ground
    truth."""
    S = SpecimenSet("m", [
        Specimen("c", "REQUEST: q?\nREPLY: fine."),
        Specimen("r", "REQUEST: q?\nREPLY: rotten.", defect_classes(R))])
    rub = Rubric("r", [Checkpoint("cp", defect_classes(R),
                                  lambda t: "rotten" in t)])
    repair = Evasion("repair", "deletes the defect",
                     lambda t: t.replace("rotten.", "fine."))
    assert attack(rub, S, (repair,)).held


def test_agreement_refuses_duplicate_ratings_instead_of_keeping_the_last():
    """A dict write kept whichever rating came last and said nothing, so
    'agreement' was measured against a coin toss over which survived."""
    S = SpecimenSet("m", [
        Specimen("c1", "REQUEST: q?\nREPLY: a"),
        Specimen("c2", "REQUEST: q?\nREPLY: b"),
        Specimen("r1", "REQUEST: q?\nREPLY: rotten", defect_classes(R))])
    cp = Checkpoint("cp", defect_classes(R), lambda t: "rotten" in t)
    rs = [Rating("a", "cp", "c1", False), Rating("a", "cp", "c2", False),
          Rating("a", "cp", "r1", True), Rating("a", "cp", "r1", False),
          Rating("b", "cp", "c1", False), Rating("b", "cp", "c2", False),
          Rating("b", "cp", "r1", True)]
    with pytest.raises(AssayError, match="CONTRADICTORY"):
        agree(cp, S, rs)


def test_power_uses_real_hit_counts_not_a_reconstruction():
    """hits was recovered as round(best_separation * n). Separation subtracts
    false alarms, so a checkpoint that false-alarmed had its detections
    understated: 4/4 read as 2/4 at a 50% false-alarm rate. A value derived
    from another derived value agrees with itself."""
    S = SpecimenSet("m",
        [Specimen(f"c{i}", f"REQUEST: q?\nREPLY: fine {i}") for i in range(4)]
        + [Specimen(f"r{i}", f"REQUEST: q?\nREPLY: rotten {i}", defect_classes(R))
           for i in range(4)])
    cp = Checkpoint("cp", defect_classes(R),
                    lambda t: "rotten" in t or "fine 0" in t or "fine 1" in t)
    a = run(Rubric("r", [cp]), S)
    assert a.checkpoints[0].false_alarm_rate == 0.5     # the condition that bit
    c = power(a).classes[0]
    assert (c.hits, c.n) == (4, 4)


# ---------------------------------------------------------------- round two

def _repo(tmp):
    import subprocess
    r = tmp / "repo"
    r.mkdir()
    for c in (["init", "-q"], ["config", "user.email", "t@t"],
              ["config", "user.name", "t"]):
        subprocess.run(["git", *c], cwd=r, check=True, capture_output=True)
    (r / "x").write_text("x")
    subprocess.run(["git", "add", "x"], cwd=r, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=r, check=True,
                   capture_output=True)
    return r


def _mat(n=6):
    bs, ij = [], []
    for i in range(n):
        bs.append(Base(f"b{i}", f"REQUEST: q{i}?\nREPLY: an ordinary answer {i}."))
        ij.append(Injection(f"br{i}", R,
                            replace_in_reply(f"an ordinary answer {i}.",
                                             f"a wholly different line {i}."),
                            applies_to=frozenset({f"b{i}"})))
    return Pack("p", bs, ij).build()


def test_a_blind_rubric_is_not_printed_as_zero_percent_evadable(tmp_path):
    """A rubric that caught nothing cannot be evaded, and printing its 0%
    beside a real 0% ranks it as unbreakable."""
    from deadcheck import build, calibrate, certify, render_markdown
    repo, m = _repo(tmp_path), _mat()
    blind = Rubric("blind", [Checkpoint("cp", defect_classes(R), lambda t: False)])
    root = repo / "certs"
    d = root / "blind"
    certify(d, blind, m, run(blind, m), calibrate(m), attack(blind, m),
            repo=repo, cert_root=root)
    reg = build([d])
    assert reg.rows[0].evasion_rate is None
    line = next(l for l in render_markdown(reg).splitlines() if "`blind`" in l)
    assert "caught nothing" in line and "0%" not in line.split("|")[6]


def test_a_bundle_with_zero_classes_is_refused_everywhere(tmp_path):
    """0/0 is vacuously consistent and reads as a clean sheet."""
    from deadcheck.recompute import check
    d = tmp_path / "c"
    d.mkdir()
    aj = {"rubric_id": "r", "specimen_set_id": "s", "material_sha": "x",
          "classes": [], "checkpoints": [], "residual": [],
          "calibration": {"floor": 0, "difficulty": 1, "best_probe": "coin",
                          "cheap_classes": [], "probes": []}}
    (d / "assay.json").write_text(json.dumps(aj))
    man = {"vac_version": "0.2",
           "evidence": [{"path": "assay.json",
                         "sha256": hashlib.sha256((d / "assay.json").read_bytes()).hexdigest()}],
           "results": {"summary": {"assay": {}},
                       "checks": [{"expect": {"classes": 0, "covered": 0, "residual": 0,
                                              "checkpoints": 0, "decoration": 0}}]}}
    (d / "vac.json").write_text(json.dumps(man))
    row, reasons = verify(d)
    assert row is None and any("measured nothing" in r for r in reasons)
    code, report = check(d)
    assert code == 1 and "EMPTY" in report


def test_cli_rejects_a_class_where_an_instance_was_meant(capsys):
    from deadcheck.cli import main
    assert main(["calibrate", "--pack", "deadcheck:Pack"]) == 2
    err = capsys.readouterr().err
    assert "names the class Pack" in err and "Traceback" not in err


def test_an_injection_returning_none_is_refused_not_crashed():
    b = Base("b", "REQUEST: q?\nREPLY: a.")
    with pytest.raises(AssayError, match="returned NoneType"):
        Pack("p", [b], [Injection("x", R, lambda t: None,
                                  applies_to=frozenset({"b"}))]).build()


def test_an_evasion_returning_none_is_refused_not_crashed():
    S = SpecimenSet("m", [Specimen("c", "REQUEST: q?\nREPLY: fine."),
                          Specimen("r", "REQUEST: q?\nREPLY: rotten.", defect_classes(R))])
    rub = Rubric("r", [Checkpoint("cp", defect_classes(R), lambda t: "rotten" in t)])
    with pytest.raises(AssayError, match="returned NoneType"):
        attack(rub, S, (Evasion("bad", "", lambda t: None),))


# -------------------------------------------------------------- round three

def test_a_blocking_rule_must_name_checkpoints_that_exist():
    """A typo in blocking() never blocks anything, so every verdict stands
    and the report calls that exhaustive: a config error as a clean sheet."""
    from deadcheck import blocking, what_flips
    S = SpecimenSet("m", [Specimen("c", "REQUEST: q?\nREPLY: fine."),
                          Specimen("r", "REQUEST: q?\nREPLY: rotten.", defect_classes(R))])
    rub = Rubric("r", [Checkpoint("cp", defect_classes(R), lambda t: "rotten" in t)])
    with pytest.raises(AssayError, match="does not have"):
        what_flips(rub, S.specimens[1], blocking("cp_ghost"))
    with pytest.raises(AssayError, match="blocks nothing"):
        blocking()


def test_the_same_bundle_cannot_be_listed_twice(tmp_path):
    from deadcheck import build, calibrate, certify
    repo, m = _repo(tmp_path), _mat()
    rub = Rubric("r", [Checkpoint("cp", defect_classes(R), lambda t: "wholly" in t)])
    d = repo / "certs" / "r"
    certify(d, rub, m, run(rub, m), calibrate(m), repo=repo, cert_root=repo / "certs")
    with pytest.raises(AssayError, match="passed twice"):
        build([d, d])


def test_recompute_rejects_counts_that_are_not_counts():
    from deadcheck.recompute import recompute
    bad = recompute({"checkpoints": [{"checkpoint_id": "cp", "detection": [5, 3],
                                      "false_alarms": [0, 4], "separation": 1.6667,
                                      "decoration": False, "untested": False}],
                     "classes": [], "residual": []})
    assert any("not a count" in b for b in bad)


def test_recompute_rejects_a_covered_class_with_no_detections():
    from deadcheck.recompute import recompute
    bad = recompute({"checkpoints": [],
                     "classes": [{"defect_class": R, "covered": True, "claimed": True,
                                  "covering_checkpoints": ["cp"], "best_separation": 0.0,
                                  "best_hits": 0, "n_specimens": 4}],
                     "residual": []})
    assert any("zero detections" in b for b in bad)


# --------------------------------------------------------------- round four

def test_a_specimen_cannot_carry_a_class_no_checkpoint_may_declare():
    """Specimen.defects skipped the id check that Checkpoint.targets runs, so
    a specimen could carry a class that could never be covered."""
    with pytest.raises(AssayError, match="snake_case"):
        Specimen("x", "REQUEST: q?\nREPLY: t", frozenset({"Bad Class"}))


def test_cli_evasions_flag_must_name_evasions(capsys):
    from deadcheck.cli import main
    code = main(["attack", "--pack", "packs.flight_v1:FLIGHT_V1",
                 "--rubric", "examples.flight_rubric:written_v2",
                 "--evasions", "packs.flight_v1:FLIGHT_V1"])
    assert code == 2
    err = capsys.readouterr().err
    assert "sequence of Evasion" in err and "Traceback" not in err


def test_agreement_over_one_shared_specimen_is_refused():
    S = SpecimenSet("m", [Specimen("c1", "REQUEST: q?\nREPLY: a"),
                          Specimen("c2", "REQUEST: q?\nREPLY: b"),
                          Specimen("r1", "REQUEST: q?\nREPLY: rotten", defect_classes(R)),
                          Specimen("r2", "REQUEST: q?\nREPLY: rotten too", defect_classes(R))])
    cp = Checkpoint("cp", defect_classes(R), lambda t: "rotten" in t)
    rs = [Rating("a", "cp", "c1", False), Rating("a", "cp", "r1", True),
          Rating("b", "cp", "r1", True), Rating("b", "cp", "r2", True)]
    with pytest.raises(AssayError, match="coin read as a result"):
        agree(cp, S, rs)


def test_a_check_whose_artifact_is_not_the_summarised_one_is_rejected(tmp_path):
    from deadcheck import calibrate, certify
    repo, m = _repo(tmp_path), _mat()
    rub = Rubric("r", [Checkpoint("cp", defect_classes(R), lambda t: "wholly" in t)])
    d = repo / "certs" / "r"
    certify(d, rub, m, run(rub, m), calibrate(m), repo=repo, cert_root=repo / "certs")
    man = json.loads((d / "vac.json").read_text())
    man["results"]["checks"][0]["artifact"] = "other.json"
    (d / "vac.json").write_text(json.dumps(man))
    row, reasons = verify(d)
    assert row is None and any("not a projection this registry recomputes" in r for r in reasons)


# --------------------------------------------------------------- round five

def test_earned_refuses_a_floor_from_other_material():
    from deadcheck import calibrate, earned
    a = run(Rubric("r", [Checkpoint("cp", defect_classes(R), lambda t: "wholly" in t)]),
            _mat())
    other = Pack("other", [Base("b", "REQUEST: q?\nREPLY: x.")],
                 [Injection("i", R, replace_in_reply("x.", "utterly y."),
                            applies_to=frozenset({"b"}))]).build()
    with pytest.raises(AssayError, match="means nothing"):
        earned(a, calibrate(other))


def test_ratchet_save_creates_the_directory(tmp_path):
    from deadcheck import calibrate, capability, load, save
    m = _mat()
    a = run(Rubric("r", [Checkpoint("cp", defect_classes(R), lambda t: "wholly" in t)]), m)
    target = tmp_path / "no" / "such" / "dir" / "b.json"
    save(capability(a, m), target)
    assert load(target)["rubric_id"] == "r"


def test_duplicate_evasion_ids_are_refused():
    S = SpecimenSet("m", [Specimen("c", "REQUEST: q?\nREPLY: fine."),
                          Specimen("r", "REQUEST: q?\nREPLY: rotten, truly.", defect_classes(R))])
    rub = Rubric("r", [Checkpoint("cp", defect_classes(R), lambda t: "rotten," in t)])
    with pytest.raises(AssayError, match="not unique"):
        attack(rub, S, (Evasion("same", "", lambda t: t.replace(",", "")),
                        Evasion("same", "", lambda t: t.upper())))


# ---------------------------------------------------------------- round six

def test_a_refusal_for_zero_classes_keeps_reasons_already_found(tmp_path):
    """The early return dropped collected reasons, so a bundle that both
    escaped its directory and measured nothing reported only the second."""
    d = tmp_path / "cert"
    d.mkdir()
    (tmp_path / "outside.txt").write_text("x")
    (d / "assay.json").write_text(json.dumps({
        "rubric_id": "r", "specimen_set_id": "s", "material_sha": "x",
        "classes": [], "checkpoints": [], "residual": [],
        "calibration": {"floor": 0, "difficulty": 1, "best_probe": "coin",
                        "cheap_classes": [], "probes": []}}))
    man = {"vac_version": "0.2",
           "evidence": [{"path": "../outside.txt", "sha256": hashlib.sha256(b"x").hexdigest()},
                        {"path": "assay.json",
                         "sha256": hashlib.sha256((d / "assay.json").read_bytes()).hexdigest()}],
           "results": {"summary": {"assay": {}}, "checks": [{"artifact": "assay.json", "expect": {"classes": 0}}]}}
    (d / "vac.json").write_text(json.dumps(man))
    row, reasons = verify(d)
    assert row is None
    assert any("escapes the bundle" in r for r in reasons)
    assert any("measured nothing" in r for r in reasons)


def test_certificate_md_names_the_underpowered_classes():
    """The manifest carried the limitation; the page a human reads did not.
    The rendered face must not read cleaner than the bundle behind it."""
    from deadcheck import calibrate
    from deadcheck.certificate import assay_json, render
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
    from flight_rubric import written_v2

    from packs.flight_v1 import FLIGHT_V1
    b = FLIGHT_V1.build()
    md = render(assay_json(written_v2, b, run(written_v2, b), calibrate(b)))
    assert "cannot support" in md and "refusal_then_compliance" in md
