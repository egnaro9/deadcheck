"""What flips the decision.

The assay asks whether a rubric can see. This asks a different question about a
different object: given a rubric, a transcript, and a rule for turning
checkpoint outcomes into a verdict, WHICH CHECKPOINTS WOULD HAVE TO BE WRONG
for the verdict to reverse?

A verdict that hangs on one checkpoint is fragile whether or not it is correct,
and a reviewer deserves to be told which one. That is the whole of it.

Search is by increasing set size and stops at `max_size`. When it stops without
exhausting the space the report SAYS SO, because a bounded search reported as a
clean result is an instrument that cannot fail.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations

from .model import AssayError, Rubric, Specimen

# A rule maps the set of checkpoint ids that FIRED to a verdict.
# True = the decision stands (approved, passed, accepted).
DecisionRule = Callable[[frozenset[str]], bool]


def no_checkpoint_fired(fired: frozenset[str]) -> bool:
    """The default: any flag blocks. Strict, and the honest starting point."""
    return not fired


class _Blocking:
    """Only the named checkpoints block. Everything else is advisory.

    A class rather than a closure so what_flips can SEE the names. A blocking
    rule that names a checkpoint the rubric does not have never blocks
    anything, every verdict STANDS, and the report says "nothing reverses it"
    with exhaustive=True. That is a config typo reading as a clean bill of
    health, and it was found by a constructed probe.
    """

    def __init__(self, ids: tuple[str, ...]) -> None:
        if not ids:
            raise AssayError("blocking() with no ids blocks nothing, so every "
                             "verdict stands by construction")
        self.blockers = frozenset(ids)

    def __call__(self, fired: frozenset[str]) -> bool:
        return not (fired & self.blockers)


def blocking(*ids: str) -> DecisionRule:
    """Only these checkpoints block. Everything else is advisory."""
    return _Blocking(ids)


def at_most(n: int) -> DecisionRule:
    """Tolerate up to n flags."""
    if n < 0:
        raise AssayError("at_most needs a non-negative count")

    def rule(fired: frozenset[str]) -> bool:
        return len(fired) <= n
    return rule


@dataclass(frozen=True)
class FlipReport:
    specimen_id: str
    rubric_id: str
    verdict: bool
    fired: tuple[str, ...]
    flip_sets: tuple[tuple[str, ...], ...]
    searched_up_to: int
    exhaustive: bool

    @property
    def fragility(self) -> int:
        """Size of the smallest set of checkpoints that would have to be wrong
        for this verdict to reverse. 1 means the decision rests on one
        predicate. 0 means nothing within the searched range flips it."""
        return len(self.flip_sets[0]) if self.flip_sets else 0

    @property
    def hangs_on_one(self) -> bool:
        return self.fragility == 1

    def summary(self) -> str:
        head = (f"{self.specimen_id}: verdict "
                f"{'STANDS' if self.verdict else 'BLOCKED'}")
        if not self.flip_sets:
            tail = (f"nothing up to size {self.searched_up_to} reverses it"
                    if self.exhaustive else
                    f"nothing up to size {self.searched_up_to} reverses it, and "
                    "the search was BOUNDED, so larger sets were not examined")
            return f"{head}; {tail}."
        shown = "; ".join("{" + ", ".join(s) + "}" for s in self.flip_sets)
        note = "" if self.exhaustive else f" (search bounded at {self.searched_up_to})"
        return (f"{head}; flips on {self.fragility} checkpoint"
                f"{'' if self.fragility == 1 else 's'}: {shown}{note}.")


def what_flips(rubric: Rubric, specimen: Specimen,
               rule: DecisionRule = no_checkpoint_fired,
               max_size: int = 2) -> FlipReport:
    """Minimal sets of checkpoints whose outcomes, if inverted, reverse the
    verdict on this specimen.

    Only MINIMAL sets are returned. Once a set of size k flips the verdict,
    supersets of it trivially do too and carry no information.
    """
    if max_size < 1:
        raise AssayError("max_size must be at least 1")

    ids = [c.id for c in rubric.checkpoints]
    unknown = getattr(rule, "blockers", frozenset()) - set(ids)
    if unknown:
        raise AssayError(
            f"blocking rule names {sorted(unknown)}, which rubric "
            f"{rubric.id!r} does not have. Nothing would ever block, so every "
            "verdict would stand and the report would call that exhaustive.")
    try:
        fired = frozenset(c.id for c in rubric.checkpoints if c.fires(specimen))
    except Exception as exc:                                     # noqa: BLE001
        raise AssayError(
            f"a checkpoint raised on specimen {specimen.id!r}: {exc!r}. A "
            "checkpoint that cannot run is not a checkpoint that passed."
        ) from exc

    verdict = rule(fired)
    ceiling = min(max_size, len(ids))

    found: list[tuple[str, ...]] = []
    for size in range(1, ceiling + 1):
        for combo in combinations(ids, size):
            flipped = fired.symmetric_difference(combo)
            if rule(flipped) != verdict:
                found.append(tuple(sorted(combo)))
        if found:
            break   # minimal size reached; larger sets add nothing

    return FlipReport(
        specimen_id=specimen.id,
        rubric_id=rubric.id,
        verdict=verdict,
        fired=tuple(sorted(fired)),
        flip_sets=tuple(sorted(found)),
        searched_up_to=ceiling,
        exhaustive=bool(found) or ceiling == len(ids),
    )


__all__ = ["DecisionRule", "FlipReport", "at_most", "blocking",
           "no_checkpoint_fired", "what_flips"]
