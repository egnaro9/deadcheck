"""The four objects an assay needs, and the three invariants that make it
measurable at all.

A rubric is only auditable if every checkpoint DECLARES what it is trying to
catch, and the specimen set contains both defective and clean material. Without
the declaration there is nothing to compute coverage against. Without clean
specimens a checkpoint that fires on everything scores perfectly, which is the
classic instrument that cannot fail.

Those are not style preferences. They are enforced in `Rubric.validate` and
`SpecimenSet.validate`, and the assay refuses to run without them.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field


class AssayError(ValueError):
    """Raised when the instrument itself is not sound enough to report a number."""


_ID = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def _check_id(kind: str, value: str) -> str:
    if not _ID.match(value):
        raise AssayError(
            f"{kind} id {value!r} must be lowercase snake_case. Ids end up in the "
            "report and in the residual row, so they are read by people.")
    return value


@dataclass(frozen=True)
class Specimen:
    """One transcript plus GROUND TRUTH about what is wrong with it.

    `defects` is the complete set of defect classes this transcript actually
    carries. An empty set means CLEAN, and clean specimens are what make a
    false-alarm rate computable. A specimen whose defects are unknown does not
    belong in an assay: guessing them would make the ground truth a second
    opinion rather than a fact.
    """

    id: str
    transcript: str
    defects: frozenset[str] = frozenset()
    note: str = ""

    def __post_init__(self) -> None:
        _check_id("specimen", self.id)
        object.__setattr__(self, "defects", frozenset(self.defects))
        # Same rule as Checkpoint.targets. Without it a specimen can carry a
        # class no checkpoint is ALLOWED to declare, so it lands in the
        # residual forever with no way to ever cover it.
        for d in self.defects:
            _check_id("defect class", d)
        if not self.transcript.strip():
            raise AssayError(f"specimen {self.id!r} has an empty transcript")

    @property
    def is_clean(self) -> bool:
        return not self.defects


@dataclass(frozen=True)
class Checkpoint:
    """One predicate a second person could apply to a transcript, plus the
    defect classes it CLAIMS to catch.

    `predicate` returns True when the checkpoint judges the transcript
    defective. It is a plain callable over the transcript text: no model in the
    loop, so the same transcript always produces the same verdict.

    `targets` may not be empty. A checkpoint that declares nothing cannot be
    scored for coverage, and an unscoreable checkpoint is how decoration
    survives review.
    """

    id: str
    targets: frozenset[str]
    predicate: Callable[[str], bool]
    description: str = ""

    def __post_init__(self) -> None:
        _check_id("checkpoint", self.id)
        object.__setattr__(self, "targets", frozenset(self.targets))
        if not self.targets:
            raise AssayError(
                f"checkpoint {self.id!r} declares no targets. A checkpoint that "
                "claims nothing cannot be measured, and this tool exists to "
                "measure checkpoints.")
        for t in self.targets:
            _check_id("defect class", t)

    def fires(self, specimen: Specimen) -> bool:
        return bool(self.predicate(specimen.transcript))


RUBRIC_KINDS = ("subject", "calibration")


@dataclass(frozen=True)
class Rubric:
    """A set of checkpoints, and a declaration of what it is FOR.

    `kind` is load-bearing. A `subject` rubric is the thing being measured:
    an external rubric, a client's, anything whose score is a finding. A
    `calibration` rubric exists to prove the instrument can produce a given
    verdict (low coverage, over-firing, evadable) and its score is NOT a
    finding: it was written against the material and will look exactly as
    good or bad as it was built to. The registry keeps the two apart and
    never ranks one against the other. Defaults to `subject` so a rubric
    loaded from someone else's tool is a subject unless someone says otherwise.
    """

    id: str
    checkpoints: tuple[Checkpoint, ...]
    description: str = ""
    kind: str = "subject"

    def __post_init__(self) -> None:
        _check_id("rubric", self.id)
        if self.kind not in RUBRIC_KINDS:
            raise AssayError(f"rubric {self.id!r}: kind must be one of "
                             f"{RUBRIC_KINDS}, not {self.kind!r}")
        object.__setattr__(self, "checkpoints", tuple(self.checkpoints))
        if not self.checkpoints:
            raise AssayError(f"rubric {self.id!r} has no checkpoints")
        seen: set[str] = set()
        for c in self.checkpoints:
            if c.id in seen:
                raise AssayError(f"duplicate checkpoint id {c.id!r} in rubric {self.id!r}")
            seen.add(c.id)

    @property
    def declared_targets(self) -> frozenset[str]:
        return frozenset().union(*(c.targets for c in self.checkpoints))


@dataclass(frozen=True)
class SpecimenSet:
    """The material an assay runs against. Needs clean specimens, or the
    false-alarm half of every number below is unmeasurable."""

    id: str
    specimens: tuple[Specimen, ...]

    def __post_init__(self) -> None:
        _check_id("specimen set", self.id)
        object.__setattr__(self, "specimens", tuple(self.specimens))
        seen: set[str] = set()
        for s in self.specimens:
            if s.id in seen:
                raise AssayError(f"duplicate specimen id {s.id!r}")
            seen.add(s.id)
        if not any(s.is_clean for s in self.specimens):
            raise AssayError(
                f"specimen set {self.id!r} contains no CLEAN specimens. Without "
                "them a checkpoint that fires on everything scores a perfect "
                "detection rate, and the assay would be an instrument that "
                "cannot fail.")
        if not any(s.defects for s in self.specimens):
            raise AssayError(
                f"specimen set {self.id!r} contains no DEFECTIVE specimens, so "
                "there is nothing for a checkpoint to detect.")

    @property
    def present_defects(self) -> frozenset[str]:
        """Defect classes actually carried by at least one specimen. Coverage is
        computed against THIS, never against what the rubric claims to target."""
        return frozenset().union(*(s.defects for s in self.specimens)) or frozenset()

    def carrying(self, defect: str) -> tuple[Specimen, ...]:
        return tuple(s for s in self.specimens if defect in s.defects)

    @property
    def clean(self) -> tuple[Specimen, ...]:
        return tuple(s for s in self.specimens if s.is_clean)


@dataclass(frozen=True)
class CoveragePolicy:
    """What it takes for a defect class to count as COVERED.

    `min_separation` is the gap a checkpoint must open between specimens
    carrying its target defect and clean specimens. `max_false_alarm_rate` is
    how often it may fire on clean material and still count.

    The defaults are strict on purpose: zero false alarms, and a checkpoint must
    catch at least half the specimens carrying its target. That matches the
    standard the reference-fleet matrix was measured to. Loosening them is a
    real decision with a real cost, which is why it is a named object and not a
    magic number buried in the scorer.
    """

    min_separation: float = 0.5
    max_false_alarm_rate: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 < self.min_separation <= 1.0:
            raise AssayError("min_separation must be in (0, 1]")
        if not 0.0 <= self.max_false_alarm_rate < 1.0:
            raise AssayError("max_false_alarm_rate must be in [0, 1)")


def defect_classes(*names: str) -> frozenset[str]:
    """Small helper so call sites read as declarations."""
    return frozenset(_check_id("defect class", n) for n in names)


def all_ids(items: Iterable) -> tuple[str, ...]:
    return tuple(i.id for i in items)


__all__ = [
    "AssayError", "Checkpoint", "CoveragePolicy", "RUBRIC_KINDS", "Rubric",
    "Specimen", "SpecimenSet", "all_ids", "defect_classes",
]
