"""The ratchet: a rubric may not quietly lose the ability to catch something.

Snapshot a rubric's measured capability, commit the snapshot, and compare every
later edit against it. Losing a defect class turns the build red and names what
stopped being detected.

The hard part is not the diff. It is that the obvious ratchet is trivial to
satisfy dishonestly, in three ways this module refuses to be fooled by:

  1. DELETE THE SPECIMEN THAT CATCHES YOU. Coverage rises, the residual
     shrinks, and the rubric got worse. The baseline therefore fingerprints the
     MATERIAL, and specimens that disappeared are reported as a finding in
     their own right rather than quietly improving the score.

  2. ADD A DEFECT CLASS. Coverage legitimately falls, because the material got
     harder. Scoring that as a regression teaches people to stop adding
     material, which is the exact opposite of what this is for. New classes are
     surfaced and are NOT regressions.

  3. NO BASELINE AT ALL. A ratchet with nothing to compare against must not
     report green. `compare` cannot be called without a baseline, and
     `RatchetReport.ok` is never True for a comparison that did not happen.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .assay import Assay
from .model import AssayError, SpecimenSet

SCHEMA = 1


def _r(x: float) -> float:
    """Round before storing. Float noise across runs is not a regression, and a
    ratchet that fires on it gets switched off within a week."""
    return round(x, 4)


def material_fingerprint(specimens: SpecimenSet) -> str:
    """Identity of the MATERIAL: which specimens, carrying which defects.

    Scores computed over different material are not comparable, so this is what
    tells a later run whether it is looking at the same question.
    """
    lines = [f"{s.id}:{','.join(sorted(s.defects))}"
             for s in sorted(specimens.specimens, key=lambda s: s.id)]
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]


def capability(assay: Assay, specimens: SpecimenSet) -> dict:
    """A serializable snapshot of what a rubric could measurably do."""
    return {
        "schema": SCHEMA,
        "rubric_id": assay.rubric_id,
        "specimen_set_id": assay.specimen_set_id,
        "material": material_fingerprint(specimens),
        "specimens": {s.id: sorted(s.defects)
                      for s in sorted(specimens.specimens, key=lambda s: s.id)},
        "policy": {"min_separation": assay.policy.min_separation,
                   "max_false_alarm_rate": assay.policy.max_false_alarm_rate},
        "coverage": _r(assay.coverage),
        "classes": {c.defect_class: {"covered": c.covered,
                                     "best_separation": _r(c.best_separation)}
                    for c in assay.classes},
        "checkpoints": {c.checkpoint_id: {"separation": _r(c.separation),
                                          "untested": c.untested}
                        for c in assay.checkpoints},
    }


def save(cap: dict, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cap, indent=1, sort_keys=True) + "\n")


def load(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise AssayError(
            f"no baseline at {p}. A ratchet with nothing to compare against "
            "cannot pass; write one with `save(capability(...))` and commit it.")
    cap = json.loads(p.read_text())
    if cap.get("schema") != SCHEMA:
        raise AssayError(
            f"baseline at {p} is schema {cap.get('schema')!r}, this build "
            f"speaks {SCHEMA}. Regenerate it deliberately rather than letting "
            "a version skew read as a clean comparison.")
    return cap


@dataclass(frozen=True)
class RatchetReport:
    rubric_id: str
    lost_classes: tuple[str, ...]          # covered before, not now: REGRESSION
    gained_classes: tuple[str, ...]
    new_decoration: tuple[str, ...]        # separated before, not now: REGRESSION
    separation_drops: tuple[tuple[str, float, float], ...]
    removed_specimens: tuple[str, ...]     # material deleted: FINDING
    new_classes: tuple[str, ...]           # material got harder: not a regression
    added_specimens: tuple[str, ...]
    material_changed: bool
    coverage_before: float
    coverage_after: float
    policy_changed: bool

    @property
    def regressions(self) -> tuple[str, ...]:
        out = [f"lost detection of {c}" for c in self.lost_classes]
        out += [f"{c} became decoration" for c in self.new_decoration]
        out += [f"{c} separation {b:+.2f} -> {a:+.2f}"
                for c, b, a in self.separation_drops]
        out += [f"specimen {s} was removed from the material"
                for s in self.removed_specimens]
        return tuple(out)

    @property
    def ok(self) -> bool:
        return not self.regressions

    def summary(self) -> str:
        if self.ok:
            head = f"RATCHET OK · {self.rubric_id}"
        else:
            head = (f"RATCHET FAILED · {self.rubric_id} · "
                    f"{len(self.regressions)} regression"
                    f"{'' if len(self.regressions) == 1 else 's'}")
        lines = [head, f"  coverage {self.coverage_before:.0%} -> "
                       f"{self.coverage_after:.0%}"]
        for r in self.regressions:
            lines.append(f"  REGRESSION: {r}")
        for c in self.gained_classes:
            lines.append(f"  gained: {c}")
        if self.new_classes:
            lines.append("  material got harder, these classes are new and are "
                         "NOT regressions: " + ", ".join(self.new_classes))
        if self.added_specimens:
            lines.append(f"  added specimens: {', '.join(self.added_specimens)}")
        if self.policy_changed:
            lines.append("  WARNING: the coverage policy changed, so these two "
                         "numbers answer slightly different questions.")
        return "\n".join(lines)


def compare(baseline: dict, assay: Assay, specimens: SpecimenSet,
            separation_tolerance: float = 0.1) -> RatchetReport:
    """Diff a current assay against a committed baseline.

    `separation_tolerance` is how far a checkpoint's separation may slip before
    it counts as a regression. It exists so that rewording a predicate does not
    fail the build over noise, and it is a named argument rather than a constant
    because loosening it is a decision someone should have to make on purpose.
    """
    if baseline["rubric_id"] != assay.rubric_id:
        raise AssayError(
            f"baseline is for rubric {baseline['rubric_id']!r}, this assay is "
            f"{assay.rubric_id!r}. Comparing them would answer a question "
            "nobody asked.")

    b_classes = baseline["classes"]
    b_specs = baseline.get("specimens", {})
    now_specs = {s.id: sorted(s.defects) for s in specimens.specimens}
    now_classes = {c.defect_class: c for c in assay.classes}
    now_cps = {c.checkpoint_id: c for c in assay.checkpoints}

    # Lost only counts where the class is still IN the material. A class that
    # vanished because its specimens were deleted is caught by removed_specimens
    # instead, which is the honest place for it.
    lost = tuple(sorted(
        name for name, b in b_classes.items()
        if b["covered"] and name in now_classes and not now_classes[name].covered))
    gained = tuple(sorted(
        name for name, c in now_classes.items()
        if c.covered and not b_classes.get(name, {}).get("covered", False)))
    new_classes = tuple(sorted(set(now_classes) - set(b_classes)))

    drops, decoration = [], []
    for cid, b in baseline["checkpoints"].items():
        cur = now_cps.get(cid)
        if cur is None or cur.untested or b.get("untested"):
            continue
        before, after = b["separation"], _r(cur.separation)
        if before > 0 and after <= 0:
            decoration.append(cid)
        elif after < before - separation_tolerance:
            drops.append((cid, before, after))

    removed = tuple(sorted(set(b_specs) - set(now_specs)))
    added = tuple(sorted(set(now_specs) - set(b_specs)))
    b_pol = baseline.get("policy", {})

    return RatchetReport(
        rubric_id=assay.rubric_id,
        lost_classes=lost,
        gained_classes=gained,
        new_decoration=tuple(sorted(decoration)),
        separation_drops=tuple(sorted(drops)),
        removed_specimens=removed,
        new_classes=new_classes,
        added_specimens=added,
        material_changed=material_fingerprint(specimens) != baseline["material"],
        coverage_before=baseline["coverage"],
        coverage_after=_r(assay.coverage),
        policy_changed=(b_pol.get("min_separation") != assay.policy.min_separation
                        or b_pol.get("max_false_alarm_rate")
                        != assay.policy.max_false_alarm_rate),
    )


__all__ = ["RatchetReport", "SCHEMA", "capability", "compare", "load",
           "material_fingerprint", "save"]
