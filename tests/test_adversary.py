"""An attacker that cannot lose is as useless as a test that cannot fail.
These pin the ways this one could report a win it did not earn.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (AssayError, Checkpoint, Evasion, Rubric, Specimen,
                       SpecimenSet, attack, defect_classes, paraphrase)

ROT = "rot"
SET = SpecimenSet("m", [
    Specimen("clean_a", "REQUEST: q?\nREPLY: an ordinary answer."),
    Specimen("rot_a", "REQUEST: q?\nREPLY: this is rotten, truly.",
             defect_classes(ROT)),
    Specimen("rot_b", "REQUEST: q?\nREPLY: also rotten, clearly.",
             defect_classes(ROT)),
])
CATCHES = Rubric("catches", [
    Checkpoint("cp_rot", defect_classes(ROT), lambda t: "rotten," in t)])
BLIND = Rubric("blind", [
    Checkpoint("cp_blind", defect_classes(ROT), lambda t: False)])


def test_a_mechanical_evasion_defeats_a_phrase_match_and_is_verified():
    """`cp_rot` matches the literal "rotten," on the raw transcript, so any of
    several mechanical rewrites defeats it. Which one wins is an artifact of
    battery order, so assert the PROPERTY: one single cheap evasion, verified
    against the rubric rather than taken on the report's word."""
    rep = attack(CATCHES, SET)
    assert not rep.held
    assert rep.evasion_rate == 1.0
    ev = rep.evaded[0]
    assert len(ev.evasion_ids) == 1
    # the returned transcript must actually not fire; the report is not trusted
    mutated = Specimen(ev.specimen_id, ev.transcript, defect_classes(ROT))
    assert not CATCHES.checkpoints[0].fires(mutated)
    assert "rotten" in ev.transcript.lower()   # the defect is still there


def test_a_rubric_that_caught_nothing_cannot_report_a_clean_attack():
    """0% evasion against 0 catches reads like strength and is the opposite."""
    rep = attack(BLIND, SET)
    assert rep.n_caught == 0
    assert rep.n_uncaught == 2
    assert rep.evasion_rate == 0.0
    assert "NO ATTACK POSSIBLE" in rep.summary()


def test_an_evasion_unsafe_for_a_class_is_never_applied_to_it():
    """Reordering preserves some defects and destroys others. An attacker that
    ignores the declaration reports wins it did not earn."""
    reorder = Evasion("reorder", "swap the halves",
                      lambda t: t.replace("rotten, truly", "truly, rotten"),
                      unsafe_for=frozenset({ROT}))
    rep = attack(CATCHES, SET, (reorder,))
    assert rep.held       # the only evasion available was off limits here


def test_attack_with_no_evasions_is_refused():
    with pytest.raises(AssayError, match="always reports HELD"):
        attack(CATCHES, SET, ())


def test_an_evasion_that_changes_nothing_is_not_a_win():
    noop = Evasion("noop", "does nothing", lambda t: t)
    assert attack(CATCHES, SET, (noop,)).held


def test_a_paraphrase_that_rewrites_to_itself_is_refused():
    with pytest.raises(AssayError, match="can never evade"):
        paraphrase("same", "booked", "booked")


def test_only_checkpoints_claiming_the_defect_count_as_catching_it():
    """An unrelated checkpoint firing must not make a specimen look caught,
    or evading it would look like defeating the rubric's actual detection."""
    noisy = Rubric("noisy", [
        Checkpoint("cp_rot", defect_classes(ROT), lambda t: False),
        Checkpoint("cp_other", defect_classes("mold"), lambda t: True),
    ])
    rep = attack(noisy, SET)
    assert rep.n_caught == 0 and rep.n_uncaught == 2


def test_a_bounded_search_that_holds_says_it_was_bounded():
    strong = Rubric("strong", [
        Checkpoint("cp_rot", defect_classes(ROT), lambda t: "rot" in t.lower())])
    rep = attack(strong, SET, max_combined=1)
    assert rep.held
    assert not rep.exhaustive
    assert "BOUNDED" in rep.summary()


def test_the_public_rubric_survives_whitespace_but_not_paraphrase():
    """The headline demo, pinned. Generic mechanical evasions are held off;
    domain rewording is not, because a keyword rubric cannot survive it. That
    limit is declared, not patched."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
    from flight_rubric import written_v2

    from deadcheck import GENERIC_EVASIONS
    from packs.flight_v1 import EVASIONS, FLIGHT_V1
    built = FLIGHT_V1.build()

    assert attack(written_v2, built, GENERIC_EVASIONS, max_combined=2).held
    broken = attack(written_v2, built, EVASIONS, max_combined=1)
    assert not broken.held
    assert broken.evasion_rate >= 0.4
