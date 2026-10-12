"""Kappa has two famous traps and both would flatter a bad checkpoint.
These pin them, plus the finding only this layer can make.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (AssayError, Checkpoint, Rating, Specimen, SpecimenSet,
                       agree, cohens_kappa, defect_classes)

ROT = "rot"
SET = SpecimenSet("m", [
    Specimen("c1", "REQUEST: q?\nREPLY: fine one"),
    Specimen("c2", "REQUEST: q?\nREPLY: fine two"),
    Specimen("c3", "REQUEST: q?\nREPLY: fine three"),
    Specimen("r1", "REQUEST: q?\nREPLY: rotten one", defect_classes(ROT)),
    Specimen("r2", "REQUEST: q?\nREPLY: rotten two", defect_classes(ROT)),
    Specimen("r3", "REQUEST: q?\nREPLY: rotten three", defect_classes(ROT)),
])
IDS = [s.id for s in SET.specimens]
CODE_SAYS_ROTTEN = Checkpoint("cp_rot", defect_classes(ROT),
                              lambda t: "rotten" in t,
                              "Fires when the reply is rotten.")


def rate(rid, verdicts):
    return [Rating(rid, "cp_rot", sid, v) for sid, v in zip(IDS, verdicts)]


TRUTH = [False, False, False, True, True, True]


def test_two_raters_matching_the_code_read_as_sound():
    r = agree(CODE_SAYS_ROTTEN, SET, rate("a", TRUTH) + rate("b", TRUTH))
    assert r.verdict == "sound"
    assert r.kappa_human == 1.0
    assert r.code_matches_humans


def test_humans_who_disagree_make_the_checkpoint_ambiguous():
    b = [False, True, False, True, False, True]
    r = agree(CODE_SAYS_ROTTEN, SET, rate("a", TRUTH) + rate("b", b))
    assert r.verdict == "ambiguous"
    assert set(r.disagreed_on) == {"c2", "r2"}


def test_humans_agreeing_with_each_other_but_not_the_code_is_misimplemented():
    """THE finding only this layer can make. Both raters apply the PROSE
    consistently and both disagree with the PREDICATE, so every assay number
    for this checkpoint describes a rule nobody wrote down."""
    prose_says = [True, True, True, False, False, False]   # the opposite rule
    r = agree(CODE_SAYS_ROTTEN, SET, rate("a", prose_says) + rate("b", prose_says))
    assert r.humans_agree
    assert not r.code_matches_humans
    assert r.verdict == "misimplemented"
    assert "PROSE AND THE PREDICATE DISAGREE" in r.summary()


def test_kappa_is_undefined_not_zero_when_both_raters_never_vary():
    """TRAP 1. Expected agreement is already 100%, so there is no 'beyond
    chance' left. Returning 0 or 1 would invent a number."""
    allyes = [True] * 6
    k, note = cohens_kappa(allyes, allyes)
    assert k is None
    assert "UNDEFINED" in note
    r = agree(CODE_SAYS_ROTTEN, SET, rate("a", allyes) + rate("b", allyes))
    assert r.kappa_human is None
    assert r.verdict == "inconclusive"
    assert set(r.constant_raters) == {"a", "b"}
    assert "NEVER VARIED" in r.summary()


def test_raw_agreement_is_reported_beside_kappa_for_the_prevalence_paradox():
    """TRAP 2. One answer dominating drags kappa toward zero even at high raw
    agreement. Reporting kappa alone would condemn a usable checkpoint, so both
    numbers always print."""
    a = [False, False, False, False, False, True]
    b = [False, False, False, False, True, True]
    k, _ = cohens_kappa(a, b)
    raw = sum(1 for x, y in zip(a, b) if x == y) / len(a)
    assert raw > 0.8 and k < 0.8          # high agreement, low kappa
    r = agree(CODE_SAYS_ROTTEN, SET, rate("a", a) + rate("b", b))
    assert "raw 83%" in r.summary() and "kappa" in r.summary()


def test_one_rater_is_not_agreement():
    with pytest.raises(AssayError, match="not a measurement"):
        agree(CODE_SAYS_ROTTEN, SET, rate("a", TRUTH))


def test_an_unrated_checkpoint_is_unmeasured_not_agreed():
    with pytest.raises(AssayError, match="unmeasured, not agreed"):
        agree(Checkpoint("cp_other", defect_classes(ROT), lambda t: True),
              SET, rate("a", TRUTH) + rate("b", TRUTH))


def test_only_specimens_every_rater_covered_are_compared():
    """A rater who skipped the hard ones must not raise the score."""
    a = rate("a", TRUTH)
    b = [r for r in rate("b", TRUTH) if r.specimen_id in {"c1", "r1"}]
    r = agree(CODE_SAYS_ROTTEN, SET, a + b)
    assert r.n_specimens == 2


def test_ratings_for_unknown_specimens_are_refused():
    bad = [Rating("a", "cp_rot", "ghost", True)] + rate("a", TRUTH) + rate("b", TRUTH)
    with pytest.raises(AssayError, match="not in"):
        agree(CODE_SAYS_ROTTEN, SET, bad)
