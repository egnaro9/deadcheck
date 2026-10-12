"""Proving the instrument.

This tool measures whether other people's rubrics can fail. If it reports
flattering numbers on a rubric that detects nothing, it is the exact defect it
was built to find. Each test below is a way this assay could lie, pinned so it
cannot start.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rubric_assay import (AssayError, Checkpoint, CoveragePolicy, Rubric,
                          Specimen, SpecimenSet, defect_classes, markdown, run)

ROT = "rot"
MOLD = "mold"


def spec(i, text, *defects):
    return Specimen(i, text, defect_classes(*defects) if defects else frozenset())


SET = SpecimenSet("fixture", [
    spec("clean_a", "nothing wrong here"),
    spec("clean_b", "also fine"),
    spec("rot_a", "this one is rotten", ROT),
    spec("rot_b", "rotten as well", ROT),
    spec("mold_a", "this one is mouldy", MOLD),
])


def cp(i, targets, pred):
    return Checkpoint(i, defect_classes(*targets), pred)


# ---------------------------------------------------------------- the guards

def test_a_rubric_that_detects_nothing_scores_zero():
    """The headline lie. Must come out 0% with a full residual."""
    blind = Rubric("blind", [cp("cp_never", [ROT, MOLD], lambda t: False)])
    a = run(blind, SET)
    assert a.coverage == 0.0
    assert set(a.residual) == {ROT, MOLD}
    assert a.checkpoints[0].separation == 0.0
    assert a.checkpoints[0].is_decoration


def test_a_checkpoint_that_fires_on_everything_is_decoration():
    """Perfect detection rate, zero separation. Subtracting the false-alarm
    rate is the only thing standing between this and a perfect score."""
    always = Rubric("always", [cp("cp_always", [ROT], lambda t: True)])
    a = run(always, SET)
    r = a.checkpoints[0]
    assert r.detection_rate == 1.0        # looks perfect
    assert r.false_alarm_rate == 1.0      # and is worthless
    assert r.separation == 0.0
    assert r.is_decoration
    assert a.coverage == 0.0              # must NOT cover rot


def test_specimen_set_without_clean_material_is_refused():
    with pytest.raises(AssayError, match="no CLEAN specimens"):
        SpecimenSet("bad", [spec("rot_a", "rotten", ROT)])


def test_specimen_set_without_defects_is_refused():
    with pytest.raises(AssayError, match="no DEFECTIVE specimens"):
        SpecimenSet("bad", [spec("clean_a", "fine"), spec("clean_b", "fine too")])


def test_checkpoint_claiming_nothing_is_refused():
    with pytest.raises(AssayError, match="declares no targets"):
        Checkpoint("cp_vague", frozenset(), lambda t: True)


def test_a_predicate_that_raises_is_an_error_not_a_pass():
    """Scoring a crash as 'did not fire' turns a broken checkpoint into a clean
    bill of health for the transcript."""
    def boom(t):
        raise RuntimeError("kaboom")

    with pytest.raises(AssayError, match="not a checkpoint that passed"):
        run(Rubric("r", [cp("cp_boom", [ROT], boom)]), SET)


# ------------------------------------------------- measured, not self-reported

def test_coverage_is_measured_against_the_material_not_the_claims():
    """A rubric cannot grade its own ambition. Claiming a class nobody tests
    must not raise coverage, and it must be named as unmeasured."""
    r = Rubric("claims_a_lot", [
        cp("cp_rot", [ROT], lambda t: "rotten" in t),
        cp("cp_ghost", ["blight"], lambda t: False),
    ])
    a = run(r, SET)
    assert a.unmeasured_targets == ("blight",)
    assert [c.defect_class for c in a.classes] == [MOLD, ROT]   # present only
    assert a.coverage == 0.5                                     # rot only
    assert a.checkpoints[1].untested


def test_a_class_nobody_claims_is_named_in_the_residual():
    r = Rubric("partial", [cp("cp_rot", [ROT], lambda t: "rotten" in t)])
    a = run(r, SET)
    assert a.undeclared_classes == (MOLD,)
    assert MOLD in a.residual
    mold = next(c for c in a.classes if c.defect_class == MOLD)
    assert not mold.claimed


def test_multi_target_checkpoint_covers_only_what_it_catches():
    """Catching one of three declared classes must not read as covering three."""
    r = Rubric("broad", [cp("cp_broad", [ROT, MOLD], lambda t: "rotten" in t)])
    a = run(r, SET)
    covered = {c.defect_class for c in a.classes if c.covered}
    assert covered == {ROT}
    assert a.residual == (MOLD,)


def test_off_target_fire_does_not_mask_a_total_miss():
    """Regression. `missed_specimens` is scoped to CLAIMING checkpoints: an
    unrelated checkpoint firing for its own reason once emptied this list and
    made a total miss read as a near miss."""
    r = Rubric("masker", [
        cp("cp_rot", [ROT], lambda t: "rotten" in t),
        cp("cp_noisy", [ROT], lambda t: "mouldy" in t),   # fires on mold_a
    ])
    a = run(r, SET)
    mold = next(c for c in a.classes if c.defect_class == MOLD)
    assert not mold.claimed
    assert mold.missed_specimens == ("mold_a",)
    assert "NO CHECKPOINT DECLARES THIS CLASS" in markdown(a)


def test_policy_strictness_changes_the_verdict_and_is_visible():
    """One false alarm must sink coverage under the default policy, and a
    loosened policy must say so in the report rather than quietly passing."""
    noisy = Rubric("noisy", [
        cp("cp_rot", [ROT], lambda t: "rotten" in t or t == "also fine"),
    ])
    strict = run(noisy, SET)
    assert strict.coverage == 0.0            # 1 clean specimen flagged

    loose = run(noisy, SET, CoveragePolicy(min_separation=0.4,
                                           max_false_alarm_rate=0.6))
    assert loose.coverage == 0.5
    assert "false alarms <= 60%" in markdown(loose)


def test_the_report_always_prints_a_residual_section():
    clean_sweep = Rubric("good", [
        cp("cp_rot", [ROT], lambda t: "rotten" in t),
        cp("cp_mold", [MOLD], lambda t: "mouldy" in t),
    ])
    a = run(clean_sweep, SET)
    assert a.coverage == 1.0
    md = markdown(a)
    assert "## Residual: what this rubric cannot see" in md
    assert "THIS material only" in md       # no clean bill of health


# --------------------------------------------------------- what flips it

from rubric_assay import at_most, blocking, no_checkpoint_fired, what_flips


def test_a_verdict_resting_on_one_checkpoint_is_named():
    r = Rubric("r", [
        cp("cp_rot", [ROT], lambda t: "rotten" in t),
        cp("cp_mold", [MOLD], lambda t: "mouldy" in t),
    ])
    rep = what_flips(r, SET.specimens[2])          # rot_a, cp_rot fires
    assert rep.verdict is False                     # blocked
    assert rep.hangs_on_one
    assert rep.flip_sets[0] == ("cp_rot",)
    assert "flips on 1 checkpoint" in rep.summary()


def test_only_minimal_flip_sets_are_reported():
    """A superset of a flipping set also flips and carries no information."""
    r = Rubric("r", [
        cp("cp_a", [ROT], lambda t: "rotten" in t),
        cp("cp_b", [ROT], lambda t: "rotten" in t),
        cp("cp_c", [MOLD], lambda t: False),
    ])
    rep = what_flips(r, SET.specimens[0], at_most(0), max_size=3)   # clean_a
    assert rep.verdict is True
    assert all(len(s) == 1 for s in rep.flip_sets)
    assert ("cp_a", "cp_b") not in rep.flip_sets


def test_an_advisory_checkpoint_cannot_flip_a_blocking_rule():
    r = Rubric("r", [
        cp("cp_block", [ROT], lambda t: "rotten" in t),
        cp("cp_advice", [MOLD], lambda t: True),
    ])
    rep = what_flips(r, SET.specimens[0], blocking("cp_block"))
    assert rep.verdict is True
    assert rep.flip_sets == (("cp_block",),)        # advisory one never appears


def test_a_bounded_search_says_it_was_bounded():
    """A cap reported as a clean result is an instrument that cannot fail."""
    r = Rubric("r", [cp(f"cp_{i}", [ROT], lambda t: False) for i in range(5)])
    rep = what_flips(r, SET.specimens[0], at_most(3), max_size=2)
    assert rep.flip_sets == ()
    assert rep.exhaustive is False
    assert "BOUNDED" in rep.summary()
