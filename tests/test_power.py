"""An interval that cannot express doubt is the same failure as a check that
cannot fail. These pin the cases where it has to.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import AssayError, power, required_n, run, wilson


def test_a_perfect_score_at_n_three_still_admits_failure():
    """THE finding this layer exists for. 3/3 is consistent with a true
    detection rate of 44%, so a board printing it as 100% reports noise."""
    lo, hi = wilson(3, 3)
    assert 0.43 < lo < 0.45 and hi == 1.0


def test_two_of_three_and_three_of_three_are_not_distinguishable():
    """The registry prints them as different numbers; the intervals overlap
    across almost their whole range."""
    a_lo, a_hi = wilson(2, 3)
    b_lo, b_hi = wilson(3, 3)
    overlap = min(a_hi, b_hi) - max(a_lo, b_lo)
    assert overlap > 0.49


def test_the_normal_approximation_lie_is_not_reproduced():
    """The normal interval for 3/3 is [1.00, 1.00], which is not a narrow
    interval but a false one. Wilson must not agree with it."""
    assert wilson(3, 3)[0] < 0.9


def test_zero_specimens_is_not_an_interval():
    with pytest.raises(AssayError, match="not an interval"):
        wilson(0, 0)


def test_nonsensical_counts_are_refused():
    with pytest.raises(AssayError, match="nonsensical"):
        wilson(5, 3)


def test_required_n_is_the_floor_for_a_perfect_score():
    n = required_n(0.5)
    assert wilson(n, n)[0] >= 0.5
    assert wilson(n - 1, n - 1)[0] < 0.5


def test_the_seed_pack_verdicts_are_interval_checked():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
    from flight_rubric import written_v2

    from packs.flight_v1 import FLIGHT_V1
    rep = power(run(written_v2, FLIGHT_V1.build()))
    # Coverage says every class is covered; power says not every verdict is
    # supported. The disagreement is the point, and power is the honest one.
    assert not rep.ok
    assert all(c.n >= 4 for c in rep.classes)
    assert "UNDERPOWERED" in rep.summary()


def test_a_covered_verdict_is_conclusive_only_when_its_floor_clears_the_bar():
    from deadcheck.power import ClassPower
    lo, hi = wilson(8, 8)
    assert ClassPower("x", 8, 8, lo, hi, covered=True, threshold=0.5).conclusive
    lo3, hi3 = wilson(3, 3)
    assert not ClassPower("x", 3, 3, lo3, hi3, covered=True,
                          threshold=0.5).conclusive


def test_an_uncovered_verdict_is_conclusive_when_its_ceiling_misses_the_bar():
    from deadcheck.power import ClassPower
    lo, hi = wilson(0, 20)
    assert ClassPower("x", 20, 0, lo, hi, covered=False,
                      threshold=0.5).conclusive
