"""Layers 7 and 9: how hard is the material, and what does a naive rubric score?

Everything else in this package measures a rubric against a specimen set. That
leaves the obvious question unasked: **is the specimen set any good?** A rubric
scoring 100% against weak material means nothing, and that is the same failure
as a checkpoint that fires on everything, one level up.

So: run a battery of deliberately naive rubrics over the material and see how
far they get.

  FLOOR       (layer 9) the best coverage any naive probe achieves. A real
              rubric's 85% means something different against a floor of 60 than
              against 20, and publishing a coverage number without its floor is
              publishing a measurement without a blank.

  DIFFICULTY  (layer 7) 1 - floor. How much of the material naive rubrics
              cannot reach.

  CHEAP CLASSES  the actionable output. Any defect class a naive probe covers
              is not testing anything, and no amount of rubric craft makes a
              score against it mean something.

The probes know NOTHING about any particular pack. They are built from the
defect class names alone, which is what keeps them naive. The sharpest of them
is a deterministic coin flip: if chance covers a class, that class is decoration
in specimen form.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from .assay import run
from .model import (AssayError, Checkpoint, CoveragePolicy, Rubric, Specimen,
                    SpecimenSet, defect_classes)


def _coin(t: str) -> bool:
    """Deterministic chance. Not random, but uncorrelated with the defect,
    which is what a control needs to be."""
    return int(hashlib.sha256(t.encode()).hexdigest(), 16) % 2 == 0


def _reply(t: str) -> str:
    return t.split("REPLY:", 1)[1].lower() if "REPLY:" in t else t.lower()


@dataclass(frozen=True)
class Probe:
    """A deliberately weak strategy, instantiated per defect class."""

    id: str
    description: str
    build: Callable[[str], Checkpoint]


def _kw(cls: str) -> Checkpoint:
    """Fire on any word taken from the defect class name itself. The laziest
    rubric anyone actually writes.

    The fallback is load-bearing. An earlier version kept only parts longer
    than three characters, so a class named `rot` produced an EMPTY word list
    and a probe that could never fire. A control that cannot fire makes
    material look harder than it is, which is the one direction calibration
    must never err in.
    """
    words = [w for w in cls.split("_") if len(w) >= 3] or [cls]
    return Checkpoint(f"kw_{cls}", defect_classes(cls),
                      lambda t, w=tuple(words): any(x in _reply(t) for x in w))


NAIVE_PROBES: tuple[Probe, ...] = (
    Probe("coin", "Deterministic coin flip. The control: uncorrelated with the "
                  "defect by construction.",
          lambda cls: Checkpoint(f"coin_{cls}", defect_classes(cls), _coin)),
    Probe("always", "Fires on everything. Catches every defect and every clean "
                    "specimen with it.",
          lambda cls: Checkpoint(f"always_{cls}", defect_classes(cls),
                                 lambda t: True)),
    Probe("never", "Fires on nothing.",
          lambda cls: Checkpoint(f"never_{cls}", defect_classes(cls),
                                 lambda t: False)),
    Probe("keyword", "Greps the reply for words lifted from the defect class "
                     "name.", _kw),
    Probe("long", "Fires when the reply is longer than average. A real "
                  "heuristic people ship.",
          lambda cls: Checkpoint(f"long_{cls}", defect_classes(cls),
                                 lambda t: len(_reply(t)) > 140)),
    Probe("hedge", "Fires on hedging language.",
          lambda cls: Checkpoint(f"hedge_{cls}", defect_classes(cls),
                                 lambda t: any(h in _reply(t) for h in
                                               ("i think", "possibly", "may be",
                                                "cannot", "unable")))),
)


@dataclass(frozen=True)
class ProbeResult:
    probe_id: str
    coverage: float
    covered_classes: tuple[str, ...]


@dataclass(frozen=True)
class Calibration:
    specimen_set_id: str
    n_specimens: int
    n_clean: int
    classes: tuple[str, ...]
    probes: tuple[ProbeResult, ...]
    cheap_classes: tuple[str, ...]      # covered by at least one naive probe

    @property
    def floor(self) -> float:
        """Layer 9. The best a naive rubric does on this material."""
        return max((p.coverage for p in self.probes), default=0.0)

    @property
    def difficulty(self) -> float:
        """Layer 7. How much of the material naive rubrics cannot reach."""
        return 1.0 - self.floor

    @property
    def best_probe(self) -> str:
        return max(self.probes, key=lambda p: p.coverage).probe_id if self.probes else ""

    @property
    def ok(self) -> bool:
        """A pack is usable when no naive probe reaches any class. A pack with
        cheap classes is not unusable, but every score against it has to be
        read with the floor beside it."""
        return not self.cheap_classes

    def summary(self) -> str:
        lines = [
            f"CALIBRATION · {self.specimen_set_id}",
            f"  {self.n_specimens} specimens ({self.n_clean} clean), "
            f"{len(self.classes)} defect classes",
            f"  floor {self.floor:.0%} (best naive probe: "
            f"{self.best_probe or 'none'})",
            f"  difficulty {self.difficulty:.0%}",
        ]
        for p in sorted(self.probes, key=lambda p: -p.coverage):
            got = ", ".join(p.covered_classes) or "nothing"
            lines.append(f"    {p.probe_id:<8} {p.coverage:>4.0%}  reaches {got}")
        if self.cheap_classes:
            lines.append("  CHEAP CLASSES, a naive probe reaches these and a "
                         "score against them means little: "
                         + ", ".join(self.cheap_classes))
        else:
            lines.append("  No naive probe reached any class. Scores against "
                         "this material are earned.")
        return "\n".join(lines)


def calibrate(specimens: SpecimenSet,
              policy: CoveragePolicy | None = None,
              probes: tuple[Probe, ...] = NAIVE_PROBES) -> Calibration:
    """Run the naive battery over a specimen set."""
    if not probes:
        raise AssayError(
            "calibration with no probes would report difficulty 100% for any "
            "material at all, including an empty box. Pass probes.")
    if not isinstance(specimens, SpecimenSet):
        hint = (" Call .build() on it first." if hasattr(specimens, "build")
                else "")
        raise AssayError(
            f"calibrate needs a SpecimenSet, got "
            f"{type(specimens).__name__}.{hint}")
    policy = policy or CoveragePolicy()
    classes = tuple(sorted(specimens.present_defects))

    results, cheap = [], set()
    for probe in probes:
        rubric = Rubric(f"probe_{probe.id}",
                        [probe.build(c) for c in classes])
        a = run(rubric, specimens, policy)
        covered = tuple(c.defect_class for c in a.classes if c.covered)
        cheap.update(covered)
        results.append(ProbeResult(probe.id, a.coverage, covered))

    return Calibration(
        specimen_set_id=specimens.id,
        n_specimens=len(specimens.specimens),
        n_clean=len(specimens.clean),
        classes=classes,
        probes=tuple(results),
        cheap_classes=tuple(sorted(cheap)),
    )


def earned(assay, cal: Calibration) -> float:
    """A coverage number with the floor subtracted out, rescaled.

    0.0 means the rubric did no better than the best naive probe; 1.0 means it
    reached everything naive rubrics could not. This is the number worth
    publishing, and it is meaningless without the calibration beside it.

    Pass the Assay, not its coverage. A floor measured on other material says
    nothing about this score, and only the Assay carries the specimen set id
    that lets this function refuse the mismatch. A bare float is accepted for
    callers that have already checked, and is on them.
    """
    if hasattr(assay, "specimen_set_id"):
        if assay.specimen_set_id != cal.specimen_set_id:
            raise AssayError(
                f"calibration is for {cal.specimen_set_id!r}, the assay is for "
                f"{assay.specimen_set_id!r}. Subtracting a floor measured on "
                "other material produces a number that means nothing.")
        assay_coverage = assay.coverage
    else:
        assay_coverage = float(assay)
    if cal.floor >= 1.0:
        raise AssayError(
            f"specimen set {cal.specimen_set_id!r} has a floor of 100%: a naive "
            "probe already covers every class, so no rubric can earn anything "
            "against it. Harden the material.")
    return max(0.0, (assay_coverage - cal.floor) / (1.0 - cal.floor))


__all__ = ["Calibration", "NAIVE_PROBES", "Probe", "ProbeResult", "calibrate",
           "earned"]
