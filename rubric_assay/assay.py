"""The assay: three numbers about a rubric, computed from artifacts only.

  SEPARATION  per checkpoint. How far it pulls specimens carrying its declared
              defect away from clean ones. A checkpoint with separation 0 is
              decoration: it says the same thing about good and bad material.

  COVERAGE    per defect class. Which classes PRESENT IN THE SPECIMEN SET does
              some checkpoint actually catch, under a stated policy. Computed
              against what the specimens carry, never against what the rubric
              claims to target, because a rubric cannot grade its own ambition.

  RESIDUAL    the classes it misses, by name, plus the classes it was never
              tested on at all. This is the row the report exists for. A rubric
              without a residual is advertising.

No model in the loop. The same rubric and specimen set always produce the same
numbers, so a disagreement about a score is a disagreement about a predicate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import (AssayError, Checkpoint, CoveragePolicy, Rubric, Specimen,
                    SpecimenSet)


@dataclass(frozen=True)
class CheckpointResult:
    checkpoint_id: str
    targets: tuple[str, ...]
    n_target: int           # specimens carrying at least one declared target
    fired_on_target: int
    n_clean: int
    fired_on_clean: int
    fired_on_other: int     # defective, but not with a defect this one claims
    n_other: int

    @property
    def detection_rate(self) -> float:
        return self.fired_on_target / self.n_target if self.n_target else 0.0

    @property
    def false_alarm_rate(self) -> float:
        return self.fired_on_clean / self.n_clean if self.n_clean else 0.0

    @property
    def separation(self) -> float:
        """detection rate minus false-alarm rate, in [-1, 1].

        Subtracting the false-alarm rate is the whole point. A checkpoint that
        fires on everything has a perfect detection rate and separation 0, which
        is the correct verdict on it.
        """
        return self.detection_rate - self.false_alarm_rate

    @property
    def is_decoration(self) -> bool:
        return self.separation <= 0.0

    @property
    def untested(self) -> bool:
        """No specimen carried anything this checkpoint claims to catch, so its
        separation is not a measurement. Reported, never silently passed."""
        return self.n_target == 0


@dataclass(frozen=True)
class ClassResult:
    defect_class: str
    n_specimens: int
    covered: bool
    claimed: bool                       # some checkpoint declares this class
    covering_checkpoints: tuple[str, ...]
    best_separation: float
    missed_specimens: tuple[str, ...]
    """Specimens carrying this class that NO CLAIMING checkpoint fired on.

    Deliberately scoped to claiming checkpoints. Asking whether *any* checkpoint
    fired lets an unrelated one firing for its own reason mask a total miss, and
    the residual section is the last place that should happen.
    """


@dataclass(frozen=True)
class Assay:
    rubric_id: str
    specimen_set_id: str
    policy: CoveragePolicy
    checkpoints: tuple[CheckpointResult, ...]
    classes: tuple[ClassResult, ...]
    undeclared_classes: tuple[str, ...]   # present in specimens, no checkpoint claims them
    unmeasured_targets: tuple[str, ...]   # claimed by a checkpoint, no specimen carries them

    @property
    def coverage(self) -> float:
        if not self.classes:
            return 0.0
        return sum(1 for c in self.classes if c.covered) / len(self.classes)

    @property
    def residual(self) -> tuple[str, ...]:
        """Classes present in the material that the rubric does NOT catch."""
        return tuple(c.defect_class for c in self.classes if not c.covered)

    @property
    def decoration(self) -> tuple[str, ...]:
        return tuple(c.checkpoint_id for c in self.checkpoints
                     if c.is_decoration and not c.untested)


def run(rubric: Rubric, specimens: SpecimenSet,
        policy: CoveragePolicy | None = None) -> Assay:
    """Run every checkpoint over every specimen and reduce to the three numbers."""
    policy = policy or CoveragePolicy()
    present = specimens.present_defects
    clean = specimens.clean

    # fired[(checkpoint_id, specimen_id)] -> bool, computed exactly once
    fired: dict[tuple[str, str], bool] = {}
    for c in rubric.checkpoints:
        for s in specimens.specimens:
            try:
                fired[(c.id, s.id)] = c.fires(s)
            except Exception as exc:                     # noqa: BLE001
                # A predicate that raises is a broken instrument, not a verdict.
                # Scoring it as "did not fire" would quietly turn a crash into a
                # clean bill of health for the transcript.
                raise AssayError(
                    f"checkpoint {c.id!r} raised on specimen {s.id!r}: {exc!r}. "
                    "A checkpoint that cannot run is not a checkpoint that passed."
                ) from exc

    cp_results = []
    for c in rubric.checkpoints:
        target_specs = [s for s in specimens.specimens if s.defects & c.targets]
        other_specs = [s for s in specimens.specimens
                       if s.defects and not (s.defects & c.targets)]
        cp_results.append(CheckpointResult(
            checkpoint_id=c.id,
            targets=tuple(sorted(c.targets)),
            n_target=len(target_specs),
            fired_on_target=sum(fired[(c.id, s.id)] for s in target_specs),
            n_clean=len(clean),
            fired_on_clean=sum(fired[(c.id, s.id)] for s in clean),
            n_other=len(other_specs),
            fired_on_other=sum(fired[(c.id, s.id)] for s in other_specs),
        ))
    by_id = {r.checkpoint_id: r for r in cp_results}

    class_results = []
    for defect in sorted(present):
        carriers = specimens.carrying(defect)
        claimers = [c for c in rubric.checkpoints if defect in c.targets]

        covering, best = [], 0.0
        for c in claimers:
            r = by_id[c.id]
            # Detection is measured against THIS class, not against the union of
            # everything the checkpoint claims. A checkpoint targeting three
            # classes and catching only one must not read as covering all three.
            hits = sum(fired[(c.id, s.id)] for s in carriers)
            rate = hits / len(carriers) if carriers else 0.0
            sep = rate - r.false_alarm_rate
            best = max(best, sep)
            if sep >= policy.min_separation and r.false_alarm_rate <= policy.max_false_alarm_rate:
                covering.append(c.id)

        missed = tuple(s.id for s in carriers
                       if not any(fired[(c.id, s.id)] for c in claimers))
        class_results.append(ClassResult(
            defect_class=defect,
            n_specimens=len(carriers),
            covered=bool(covering),
            claimed=bool(claimers),
            covering_checkpoints=tuple(sorted(covering)),
            best_separation=best,
            missed_specimens=missed,
        ))

    declared = rubric.declared_targets
    return Assay(
        rubric_id=rubric.id,
        specimen_set_id=specimens.id,
        policy=policy,
        checkpoints=tuple(cp_results),
        classes=tuple(class_results),
        undeclared_classes=tuple(sorted(present - declared)),
        unmeasured_targets=tuple(sorted(declared - present)),
    )


__all__ = ["Assay", "CheckpointResult", "ClassResult", "run"]
