"""How many specimens does a class need before its verdict means anything?

Calibration asks whether the material is hard. This asks whether there is
ENOUGH of it. They are different questions and the second one bit this repo:
the seed pack shipped with one defective specimen per class, a coin flip
covered two of three classes on luck, and the fix was more specimens rather
than a better rubric.

A checkpoint's detection rate on a class is a binomial proportion over the
specimens carrying it, so it comes with an interval. At n = 3, observing 3 of 3
gives a 95% Wilson interval of about **[0.44, 1.00]**: a perfect score is
consistent with a true detection rate of 44%. And 2 of 3 gives about
[0.21, 0.94]. **Those intervals overlap almost entirely, so a board printing
2/3 and 3/3 as different numbers is reporting noise as a ranking.**

Wilson rather than the normal approximation on purpose. The normal interval
for 3 of 3 is [1.00, 1.00], which is not a wide interval, it is a false one,
and a confidence interval that cannot express doubt is the same failure as a
check that cannot fail.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .assay import Assay
from .model import AssayError, CoveragePolicy

Z95 = 1.959963984540054


def wilson(hits: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Undefined at n = 0: returning (0, 1) would look like a measurement of
    total ignorance rather than the absence of one, and returning (0, 0) would
    be worse.
    """
    if n < 0 or hits < 0 or hits > n:
        raise AssayError(f"nonsensical counts: {hits} of {n}")
    if n == 0:
        raise AssayError(
            "no specimens: an interval over zero observations is not a wide "
            "interval, it is not an interval")
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z / d) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def required_n(threshold: float, z: float = Z95, cap: int = 2000) -> int:
    """Smallest n where a PERFECT score clears `threshold` at its lower bound.

    This is the floor, not a recommendation: it assumes the checkpoint never
    misses. Any real miss pushes the requirement higher.
    """
    if not 0 < threshold < 1:
        raise AssayError("threshold must be in (0, 1)")
    for n in range(1, cap + 1):
        if wilson(n, n, z)[0] >= threshold:
            return n
    raise AssayError(f"no n below {cap} reaches a lower bound of {threshold}")


@dataclass(frozen=True)
class ClassPower:
    defect_class: str
    n: int
    hits: int                 # best claiming checkpoint's detections
    lo: float
    hi: float
    covered: bool
    threshold: float

    @property
    def conclusive(self) -> bool:
        """The verdict survives its own interval: a covered class whose LOWER
        bound still clears the bar, or an uncovered class whose UPPER bound
        does not reach it."""
        return self.lo >= self.threshold if self.covered \
            else self.hi < self.threshold

    @property
    def needed(self) -> int:
        return required_n(self.threshold)


@dataclass(frozen=True)
class PowerReport:
    specimen_set_id: str
    threshold: float
    classes: tuple[ClassPower, ...]

    @property
    def underpowered(self) -> tuple[str, ...]:
        return tuple(c.defect_class for c in self.classes if not c.conclusive)

    @property
    def ok(self) -> bool:
        return not self.underpowered

    def summary(self) -> str:
        lines = [f"POWER · {self.specimen_set_id} · "
                 f"{'CONCLUSIVE' if self.ok else 'UNDERPOWERED'}",
                 f"  95% Wilson intervals against a {self.threshold:.2f} bar"]
        for c in self.classes:
            mark = "" if c.conclusive else "  <- inconclusive"
            lines.append(f"    {c.defect_class:<28} {c.hits}/{c.n} "
                         f"[{c.lo:.2f}, {c.hi:.2f}]{mark}")
        if self.underpowered:
            need = max(c.needed for c in self.classes)
            lines.append(
                f"  {len(self.underpowered)} class(es) cannot support their "
                f"own verdict at this sample size. A PERFECT score needs "
                f"n >= {need} to clear {self.threshold:.2f} at the lower "
                "bound; any miss needs more.")
        else:
            lines.append("  every verdict survives its own interval.")
        return "\n".join(lines)


def power(assay: Assay, policy: CoveragePolicy | None = None) -> PowerReport:
    """Interval-check every class verdict in an assay."""
    policy = policy or assay.policy
    rows = []
    for c in assay.classes:
        # The REAL hit count, carried through from the assay. An earlier version
        # reconstructed it from best_separation, which subtracts false alarms,
        # so any checkpoint that false-alarmed had its detections understated
        # and its interval pushed down: 4/4 read as 2/4 with a 50% false-alarm
        # rate. A value derived from another derived value agrees with itself.
        lo, hi = wilson(c.best_hits, c.n_specimens)
        rows.append(ClassPower(c.defect_class, c.n_specimens, c.best_hits,
                               lo, hi, c.covered, policy.min_separation))
    return PowerReport(assay.specimen_set_id, policy.min_separation,
                       tuple(rows))


__all__ = ["ClassPower", "PowerReport", "Z95", "power", "required_n", "wilson"]
