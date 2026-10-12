"""The claim a registry rests on: does the taxonomy transfer between domains?

If a defect class only describes one domain, a board comparing two domains is
comparing nothing. These pin what transferred, what did not, and the ground
truth bug that building the second pack exposed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples"))

from decisions_rubric import decisions_v1
from flight_rubric import written_v2

from deadcheck import calibrate, power, run
from packs.decisions_v1 import DECISIONS_V1
from packs.flight_v1 import FLIGHT_V1


def test_three_classes_transfer_and_one_was_missing():
    """The taxonomy carries across. The fourth class exists because flight
    transcripts are single-turn and cannot express an ageing approval."""
    flight = FLIGHT_V1.build().present_defects
    decisions = DECISIONS_V1.build().present_defects
    assert flight < decisions                       # proper subset
    assert decisions - flight == {"stale_approval"}


def test_the_rubric_does_not_transfer_at_all():
    """THE finding. A rubric certified on one pack says nothing about another:
    the flight rubric scores zero here and two of its three checkpoints
    collapse to decoration."""
    a = run(written_v2, DECISIONS_V1.build())
    assert a.coverage == 0.0
    assert len(a.decoration) >= 2
    assert a.undeclared_classes == ("stale_approval",)


def test_the_decisions_pack_is_hard():
    cal = calibrate(DECISIONS_V1.build())
    assert cal.floor == 0.0, cal.summary()
    assert cal.cheap_classes == ()
    assert len(cal.classes) == 4


def test_the_decisions_rubric_is_conclusive_where_flight_is_not():
    """Four specimens per class AND a rubric that catches all of them, so
    every interval clears the bar. The flight pack cannot say this."""
    rep = power(run(decisions_v1, DECISIONS_V1.build()))
    assert rep.ok, rep.summary()
    assert all(c.n >= 4 and c.hits == c.n for c in rep.classes)


def test_clean_bases_carry_no_other_class(tmp_path):
    """Regression for the ground truth bug. A clean base read 'granted at the
    700 kg payload assumption': a quantity with no revision, which is a trace
    of confident_staleness inside material labelled clean. It made a correct
    checkpoint look noisy and cost that class its coverage."""
    built = DECISIONS_V1.build()
    unrevisioned = next(c for c in decisions_v1.checkpoints
                        if c.id == "cp_unrevisioned_value")
    offenders = [s.id for s in built.clean if unrevisioned.fires(s)]
    assert offenders == [], offenders
