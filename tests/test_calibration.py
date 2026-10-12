"""Calibration has to be able to call material EASY, or it is a rubber stamp.
These build deliberately weak packs and check that it says so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (AssayError, Base, Injection, Pack, calibrate,
                       defect_classes, earned, replace_in_reply)

ROOT = Path(__file__).resolve().parents[1]


def _material(bid_count: int, defect_text: str, cls: str = "rot", salt: str = ""):
    """Build material directly; calibrate takes a SpecimenSet, not a Pack.

    `salt` varies the CLEAN text as well as the defective text. Without it,
    repeated packs share one clean specimen, so the false-alarm side of every
    probe has a single fixed outcome and sixteen "trials" are really one.
    """
    bases, injs = [], []
    for i in range(bid_count):
        bid = f"b{i}"
        clean = f"REQUEST: question {i}{salt}?\nREPLY: an ordinary answer {salt} number {i}."
        bases.append(Base(bid, clean))
        injs.append(Injection(
            f"{bid}__break", cls,
            replace_in_reply(f"an ordinary answer {salt} number {i}.", defect_text),
            applies_to=frozenset({bid})))
    return Pack("p", bases, injs).build()


def test_a_pack_whose_defect_is_the_class_name_is_called_cheap():
    """The keyword probe greps for words from the class name. If the material
    hands it the answer, calibration must say the class is cheap."""
    cal = calibrate(_material(4, "this reply is rotten through and through", "rot"))
    assert "rot" in cal.cheap_classes
    assert cal.floor > 0
    assert not cal.ok
    assert "CHEAP CLASSES" in cal.summary()


def test_a_one_specimen_per_class_pack_is_reachable_by_chance():
    """The finding that forced the public pack to grow: with one defective
    specimen per class, a coin flip covers it whenever luck falls that way.

    Asserted across many one-specimen packs rather than one, because whether
    any single pack gets covered depends on a hash. The hazard is that SOME of
    them do. A pack with eight specimens per class has none.
    """
    tinies = [calibrate(_material(1, f"a different sentence number {i}", "rot",
                                  salt=f"v{i}"))
              for i in range(16)]
    assert any(c.floor > 0 for c in tinies), (
        "chance never covered a one-specimen pack, so the hazard this test "
        "documents is unproven and the test is not measuring anything")
    big = calibrate(_material(8, "a completely different sentence entirely", "rot"))
    assert big.floor == 0.0


def test_calibration_with_no_probes_is_refused():
    with pytest.raises(AssayError, match="including an empty box"):
        calibrate(_material(3, "a different sentence"), probes=())


def test_handing_calibrate_a_pack_says_what_to_do():
    pack = Pack("p", [Base("b0", "REQUEST: q?\nREPLY: an answer.")],
                [Injection("b0__x", "rot",
                           replace_in_reply("an answer.", "a rotten answer."),
                           applies_to=frozenset({"b0"}))])
    with pytest.raises(AssayError, match=r"Call \.build\(\) on it first"):
        calibrate(pack)


def test_earned_refuses_material_a_naive_probe_already_solves():
    cal = calibrate(_material(4, "this reply is rotten", "rot"))
    if cal.floor >= 1.0:
        with pytest.raises(AssayError, match="Harden the material"):
            earned(1.0, cal)


def test_earned_subtracts_the_floor():
    cal = calibrate(_material(8, "a completely different sentence entirely", "rot"))
    assert cal.floor == 0.0
    assert earned(1.0, cal) == 1.0
    assert earned(0.0, cal) == 0.0


def test_the_always_probe_cannot_score_by_firing_on_everything():
    """The control that keeps the control honest: a probe flagging every
    specimen has a perfect detection rate and must still reach nothing."""
    cal = calibrate(_material(4, "a completely different sentence entirely", "rot"))
    always = next(p for p in cal.probes if p.probe_id == "always")
    assert always.coverage == 0.0
    assert always.covered_classes == ()


def test_the_public_pack_stays_hard():
    """Regression guard on the shipped material. If a later edit makes any
    class reachable by a naive probe, every published score against this pack
    becomes unreadable, so this test is the thing standing in the way."""
    sys.path.insert(0, str(ROOT))
    from packs.flight_v1 import FLIGHT_V1

    cal = calibrate(FLIGHT_V1.build())
    assert cal.floor == 0.0, cal.summary()
    assert cal.cheap_classes == (), cal.summary()
    assert len(cal.classes) == 3
    # Assert the REQUIREMENT, not the count: deadcheck.power says a perfect
    # score needs n >= 4 per class to clear the 0.50 bar at its lower bound,
    # and the pack grew from 3 to 4 for exactly that reason.
    from collections import Counter
    per_class = Counter(c for s in FLIGHT_V1.build().specimens for c in s.defects)
    assert min(per_class.values()) >= 4, per_class
    assert cal.n_clean == len(FLIGHT_V1.bases)
