"""Layer 8: can a second person apply this checkpoint and get the same answer?

Every rubric in this field claims its checkpoints are "objective" or "a
predicate a second person could apply". That claim is measurable and almost
nobody measures it. Psychometrics has had the tool since 1960.

A checkpoint has TWO definitions, and they can disagree:

  the PROSE      what a human reviewer reads in `Checkpoint.description`
  the PREDICATE  what the code actually runs

So this measures three things, and the third is the one nothing else here can
see:

  HUMAN vs HUMAN   low agreement means the DESCRIPTION is ambiguous.
  HUMAN vs CODE    humans agreeing with each other but not with the predicate
                   means the prose and the code describe different checkpoints,
                   and every number the assay ever produced was about the one
                   nobody wrote down.
  RAW vs KAPPA     reported side by side on purpose, see below.

**Kappa's two traps, both handled.** It is UNDEFINED when expected agreement
reaches 1, which happens when both raters answer the same way on every
specimen: the denominator is zero and there is no "beyond chance" left to
measure. Returning 0 or 1 there would be an invented number. And the prevalence
paradox means a checkpoint with 95% raw agreement can post a near-zero kappa
when one answer dominates, so reporting kappa alone would condemn a fine
checkpoint. Both numbers are always printed.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .model import AssayError, Checkpoint, Specimen, SpecimenSet

# A checkpoint is sound when humans agree with each other AND with the code.
# 0.8 is the conventional "substantial agreement" line in the psychometrics
# literature; it is a convention, not a law, which is why it is an argument.
SUBSTANTIAL = 0.8


@dataclass(frozen=True)
class Rating:
    """One human's verdict on one specimen for one checkpoint.

    `fired` is what the rater judged, reading the checkpoint's PROSE and the
    transcript, without seeing the predicate. A rater who reads the code is
    measuring nothing; that cannot be detected here and has to be handled by
    how the ratings are collected.
    """

    rater_id: str
    checkpoint_id: str
    specimen_id: str
    fired: bool


def cohens_kappa(a: Sequence[bool], b: Sequence[bool]) -> tuple[float | None, str]:
    """Agreement corrected for chance. Returns (kappa, note).

    kappa is None when it is UNDEFINED rather than zero. Callers must print the
    note; collapsing "undefined" into a number is how an unmeasurable pair
    starts looking like a measured one.
    """
    if len(a) != len(b):
        raise AssayError("rating vectors differ in length")
    n = len(a)
    if n == 0:
        return None, "no overlapping specimens: nothing to compare"

    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    expected = pa * pb + (1 - pa) * (1 - pb)

    if expected >= 1.0:
        return None, (
            "UNDEFINED: both raters gave the same answer on every specimen, so "
            "chance agreement is already 100% and there is nothing beyond it "
            "to measure. Raw agreement is the only honest number here")
    return (observed - expected) / (1 - expected), ""


@dataclass(frozen=True)
class RaterCheck:
    rater_id: str
    n: int
    varied: bool                 # did this rater ever say both yes and no
    raw_vs_code: float
    kappa_vs_code: float | None
    kappa_note: str


@dataclass(frozen=True)
class AgreementResult:
    checkpoint_id: str
    n_specimens: int
    raters: tuple[str, ...]
    raw_human: float | None       # pairwise-mean raw agreement between humans
    kappa_human: float | None
    kappa_note: str
    disagreed_on: tuple[str, ...]  # specimens where humans split
    vs_code: tuple[RaterCheck, ...]
    constant_raters: tuple[str, ...]

    @property
    def humans_agree(self) -> bool:
        return self.kappa_human is not None and self.kappa_human >= SUBSTANTIAL

    @property
    def code_matches_humans(self) -> bool:
        return bool(self.vs_code) and all(
            r.kappa_vs_code is not None and r.kappa_vs_code >= SUBSTANTIAL
            for r in self.vs_code)

    @property
    def verdict(self) -> str:
        if self.constant_raters:
            return "inconclusive"
        if not self.humans_agree:
            return "ambiguous"
        if not self.code_matches_humans:
            return "misimplemented"
        return "sound"

    def summary(self) -> str:
        k = "undefined" if self.kappa_human is None else f"{self.kappa_human:+.2f}"
        raw = "n/a" if self.raw_human is None else f"{self.raw_human:.0%}"
        lines = [
            f"AGREEMENT · {self.checkpoint_id} · {self.verdict.upper()}",
            f"  {len(self.raters)} raters over {self.n_specimens} specimens",
            f"  human vs human: raw {raw}, kappa {k}",
        ]
        if self.kappa_note:
            lines.append(f"    {self.kappa_note}")
        for r in self.vs_code:
            rk = "undefined" if r.kappa_vs_code is None else f"{r.kappa_vs_code:+.2f}"
            lines.append(f"  {r.rater_id} vs code: raw {r.raw_vs_code:.0%}, "
                         f"kappa {rk}")
        if self.disagreed_on:
            lines.append("  humans split on: " + ", ".join(self.disagreed_on))
        if self.constant_raters:
            lines.append("  NEVER VARIED, so their agreement carries no "
                         "information: " + ", ".join(self.constant_raters))
        if self.verdict == "misimplemented":
            lines.append("  THE PROSE AND THE PREDICATE DISAGREE. Raters agree "
                         "with each other and not with the code, so every assay "
                         "number for this checkpoint describes a rule nobody "
                         "wrote down.")
        return "\n".join(lines)


def agree(checkpoint: Checkpoint, specimens: SpecimenSet,
          ratings: Iterable[Rating]) -> AgreementResult:
    """Score one checkpoint's human ratings against each other and the code."""
    mine = [r for r in ratings if r.checkpoint_id == checkpoint.id]
    if not mine:
        raise AssayError(
            f"no ratings for checkpoint {checkpoint.id!r}. An unrated "
            "checkpoint is unmeasured, not agreed.")

    known = {s.id: s for s in specimens.specimens}
    unknown = sorted({r.specimen_id for r in mine} - set(known))
    if unknown:
        raise AssayError(
            f"ratings reference specimens not in {specimens.id!r}: "
            + ", ".join(unknown))

    by_rater: dict[str, dict[str, bool]] = {}
    for r in mine:
        by_rater.setdefault(r.rater_id, {})[r.specimen_id] = r.fired
    raters = tuple(sorted(by_rater))
    if len(raters) < 2:
        raise AssayError(
            f"checkpoint {checkpoint.id!r} has ratings from one rater "
            f"({raters[0]!r}). Agreement needs at least two; a single rater "
            "agreeing with themselves is not a measurement.")

    # Only specimens EVERY rater covered. Comparing different subsets would let
    # a rater who skipped the hard ones raise the score.
    shared = sorted(set.intersection(*(set(v) for v in by_rater.values())))
    if not shared:
        raise AssayError(
            f"checkpoint {checkpoint.id!r}: no specimen was rated by every "
            "rater, so there is nothing to compare.")

    vectors = {rid: [by_rater[rid][s] for s in shared] for rid in raters}
    constant = tuple(r for r in raters if len(set(vectors[r])) == 1)

    # pairwise mean, so three or more raters do not collapse to the first pair
    pairs = [(x, y) for i, x in enumerate(raters) for y in raters[i + 1:]]
    raws = [sum(1 for p, q in zip(vectors[x], vectors[y]) if p == q) / len(shared)
            for x, y in pairs]
    kappas, notes = [], []
    for x, y in pairs:
        k, note = cohens_kappa(vectors[x], vectors[y])
        if k is None:
            notes.append(f"{x} vs {y}: {note}")
        else:
            kappas.append(k)

    code = [checkpoint.fires(known[s]) for s in shared]
    checks = []
    for rid in raters:
        k, note = cohens_kappa(vectors[rid], code)
        checks.append(RaterCheck(
            rater_id=rid, n=len(shared),
            varied=len(set(vectors[rid])) > 1,
            raw_vs_code=sum(1 for p, q in zip(vectors[rid], code) if p == q)
            / len(shared),
            kappa_vs_code=k, kappa_note=note))

    split = tuple(s for i, s in enumerate(shared)
                  if len({vectors[r][i] for r in raters}) > 1)

    return AgreementResult(
        checkpoint_id=checkpoint.id,
        n_specimens=len(shared),
        raters=raters,
        raw_human=sum(raws) / len(raws),
        kappa_human=sum(kappas) / len(kappas) if kappas else None,
        kappa_note="; ".join(notes),
        disagreed_on=split,
        vs_code=tuple(checks),
        constant_raters=constant,
    )


__all__ = ["AgreementResult", "RaterCheck", "Rating", "SUBSTANTIAL", "agree",
           "cohens_kappa"]
