"""The ratchet has to refuse the three ways a capability gate is gamed:
deleting the specimen that catches you, adding material and calling the lower
score a regression, and having no baseline at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (AssayError, Checkpoint, CoveragePolicy, Rubric,
                       Specimen, SpecimenSet, capability, compare,
                       defect_classes, load, run, save)

ROT, MOLD = "rot", "mold"


def spec(i, text, *d):
    return Specimen(i, text, defect_classes(*d) if d else frozenset())


def cp(i, targets, pred):
    return Checkpoint(i, defect_classes(*targets), pred)


BASE_SET = SpecimenSet("m", [
    spec("clean_a", "fine"), spec("clean_b", "also fine"),
    spec("rot_a", "rotten", ROT), spec("mold_a", "mouldy", MOLD),
])

GOOD = Rubric("r", [
    cp("cp_rot", [ROT], lambda t: "rotten" in t),
    cp("cp_mold", [MOLD], lambda t: "mouldy" in t),
])
WEAKENED = Rubric("r", [
    cp("cp_rot", [ROT], lambda t: "rotten" in t),
    cp("cp_mold", [MOLD], lambda t: False),      # stopped catching mold
])


def base():
    return capability(run(GOOD, BASE_SET), BASE_SET)


def test_losing_a_defect_class_fails_the_ratchet_by_name():
    rep = compare(base(), run(WEAKENED, BASE_SET), BASE_SET)
    assert not rep.ok
    assert rep.lost_classes == (MOLD,)
    assert "lost detection of mold" in rep.summary()


def test_deleting_the_specimen_that_catches_you_is_a_finding_not_a_pass():
    """Weaken the rubric AND delete the specimen that would have caught it.

    Coverage is 100% before and 100% after, because the only class the rubric
    stopped detecting is no longer in the material. The regression is perfectly
    invisible in the headline number, which is exactly why the baseline
    fingerprints the material and not just the scores.
    """
    trimmed = SpecimenSet("m", [s for s in BASE_SET.specimens if s.id != "mold_a"])
    rep = compare(base(), run(WEAKENED, trimmed), trimmed)
    assert rep.coverage_before == rep.coverage_after == 1.0   # nothing to see
    assert rep.lost_classes == ()                             # and nothing lost
    assert not rep.ok                                         # but NOT ok
    assert rep.removed_specimens == ("mold_a",)
    assert rep.material_changed
    assert "was removed from the material" in rep.summary()


def test_adding_a_harder_class_is_not_a_regression():
    """New material lowers coverage legitimately. Scoring that as a regression
    teaches people to stop adding specimens."""
    harder = SpecimenSet("m", list(BASE_SET.specimens) + [spec("blight_a", "blighted", "blight")])
    rep = compare(base(), run(GOOD, harder), harder)
    assert rep.coverage_after < rep.coverage_before
    assert rep.new_classes == ("blight",)
    assert rep.ok
    assert "NOT regressions" in rep.summary()


def test_a_missing_baseline_cannot_pass(tmp_path):
    with pytest.raises(AssayError, match="cannot pass"):
        load(tmp_path / "nope.json")


def test_a_schema_skew_cannot_pass(tmp_path):
    p = tmp_path / "b.json"
    cap = base()
    cap["schema"] = 99
    save(cap, p)
    with pytest.raises(AssayError, match="speaks"):
        load(p)


def test_a_baseline_for_another_rubric_is_refused():
    other = capability(run(Rubric("other", list(GOOD.checkpoints)), BASE_SET), BASE_SET)
    with pytest.raises(AssayError, match="question nobody asked"):
        compare(other, run(GOOD, BASE_SET), BASE_SET)


def test_a_checkpoint_becoming_decoration_is_a_regression():
    rep = compare(base(), run(WEAKENED, BASE_SET), BASE_SET)
    assert "cp_mold" in rep.new_decoration


def test_an_unchanged_rubric_round_trips_green(tmp_path):
    p = tmp_path / "b.json"
    save(base(), p)
    rep = compare(load(p), run(GOOD, BASE_SET), BASE_SET)
    assert rep.ok
    assert not rep.material_changed
    assert "RATCHET OK" in rep.summary()


def test_a_policy_change_is_surfaced_not_swallowed():
    loose = run(GOOD, BASE_SET, CoveragePolicy(min_separation=0.2,
                                               max_false_alarm_rate=0.3))
    rep = compare(base(), loose, BASE_SET)
    assert rep.policy_changed
    assert "different questions" in rep.summary()
