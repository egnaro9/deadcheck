"""Layer 3: attack the rubric.

The assay says what a rubric catches on the material you have. This asks the
harder question: **of the defects it does catch, which can be made to slip?**

The method is the one from layer 2, pointed the other way. Do not mutate a
transcript until the rubric goes quiet, because the cheapest way to silence a
rubric is to delete the defect, and that is not an evasion, it is a repair. An
EVASION here is a transformation DECLARED defect-preserving, so when the rubric
stops firing the defect is still present by construction.

Preservation is declared per defect class and must be, because it genuinely
varies: swapping two sentences preserves `confident_staleness` and DESTROYS
`refusal_then_compliance`, whose whole definition is that compliance follows the
decline. An attacker that ignores that reports wins it did not earn, so
`unsafe_for` is checked before an evasion is ever applied.

Nothing here is a judgement about whether a transcript "still feels wrong". The
library ships only transformations whose preservation is mechanical. Domain
packs ship their own paraphrases, where the author is the one making the claim.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import combinations

from .model import AssayError, Rubric, Specimen, SpecimenSet


@dataclass(frozen=True)
class Evasion:
    """A transformation that hides a defect without removing it.

    `unsafe_for` names defect classes whose DEFINITION this transformation
    might destroy. The attacker will not apply it to a specimen carrying one.
    An empty set is a claim that the transformation is safe for every class,
    and that claim is the author's to defend.
    """

    id: str
    description: str
    apply: Callable[[str], str]
    unsafe_for: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "unsafe_for", frozenset(self.unsafe_for))

    def safe_for(self, specimen: Specimen) -> bool:
        return not (specimen.defects & self.unsafe_for)


def _reply_parts(t: str) -> tuple[str, str]:
    if "REPLY:" not in t:
        return "", t
    head, reply = t.split("REPLY:", 1)
    return head + "REPLY:", reply


def _in_reply(fn: Callable[[str], str]) -> Callable[[str], str]:
    """Apply a transformation to the reply only, so the request stays fixed.
    Several checkpoints compare the two halves, and silently editing the
    request would manufacture evasions that say nothing about the rubric."""
    def apply(t: str) -> str:
        head, reply = _reply_parts(t)
        return head + fn(reply)
    return apply


def _swap_case_first_letters(r: str) -> str:
    return " ".join(w[:1].upper() + w[1:] if w else w for w in r.split(" "))


def _collapse_punctuation(r: str) -> str:
    return r.replace(",", "").replace(";", "")


def _double_spaces(r: str) -> str:
    return r.replace(" ", "  ")


def _pad_tail(r: str) -> str:
    return r.rstrip() + " Let me know if you would like anything adjusted."


def _pad_head(r: str) -> str:
    return " Happy to help with this." + r


# The generic battery. Every one of these is mechanically defect-preserving:
# none adds, removes or reorders a claim, a decline or a field value. They are
# the transformations a careless checkpoint trips over, not clever ones.
GENERIC_EVASIONS: tuple[Evasion, ...] = (
    Evasion("recase", "Capitalise every word. Breaks a case-sensitive match.",
            _in_reply(_swap_case_first_letters)),
    Evasion("depunctuate", "Remove commas and semicolons. Breaks a phrase "
                           "match that spans one.",
            _in_reply(_collapse_punctuation)),
    Evasion("respace", "Double every space. Breaks a multi-word phrase match.",
            _in_reply(_double_spaces)),
    Evasion("pad_tail", "Append an innocuous closing sentence. Breaks a "
                        "length or position heuristic.",
            _in_reply(_pad_tail)),
    Evasion("pad_head", "Prepend an innocuous opening sentence. Breaks a "
                        "position heuristic and shifts every offset.",
            _in_reply(_pad_head)),
)


@dataclass(frozen=True)
class Evaded:
    specimen_id: str
    defects: tuple[str, ...]
    checkpoint_ids: tuple[str, ...]     # the ones that fired before
    evasion_ids: tuple[str, ...]        # the cheapest combination that silenced them
    transcript: str                     # the surviving-defect, unflagged transcript


@dataclass(frozen=True)
class AttackReport:
    rubric_id: str
    specimen_set_id: str
    n_caught: int                       # defective specimens the rubric flagged
    n_uncaught: int                     # it never flagged these; nothing to evade
    evaded: tuple[Evaded, ...]
    searched_up_to: int
    exhaustive: bool

    @property
    def evasion_rate(self) -> float:
        """Of the defects this rubric DOES catch, the fraction that can be
        made to slip. Zero is the only comfortable number."""
        return len(self.evaded) / self.n_caught if self.n_caught else 0.0

    @property
    def held(self) -> bool:
        return not self.evaded

    def summary(self) -> str:
        head = (f"ATTACK · {self.rubric_id} vs {self.specimen_set_id}\n"
                f"  {self.n_caught} caught, {self.n_uncaught} never caught "
                f"(nothing to evade there)")
        if self.n_caught == 0:
            return (head + "\n  NO ATTACK POSSIBLE: this rubric caught nothing, "
                    "so an evasion rate of 0% would mean the opposite of what "
                    "it reads like.")
        lines = [head, f"  evasion rate {self.evasion_rate:.0%} "
                       f"({len(self.evaded)}/{self.n_caught})"]
        for e in self.evaded:
            lines.append(f"    {e.specimen_id} slips past "
                         f"{', '.join(e.checkpoint_ids)} via "
                         f"{' + '.join(e.evasion_ids)}")
        if self.held:
            tail = ("  HELD against this battery"
                    if self.exhaustive else
                    "  HELD against this battery, but the search was BOUNDED "
                    f"at {self.searched_up_to} combined evasions")
            lines.append(tail)
        return "\n".join(lines)


def attack(rubric: Rubric, specimens: SpecimenSet,
           evasions: tuple[Evasion, ...] = GENERIC_EVASIONS,
           max_combined: int = 2) -> AttackReport:
    """Find the cheapest transformation that hides a defect this rubric catches.

    Only specimens the rubric ALREADY flags are attacked. A defect it never
    caught needs no evasion, and counting those as successes would make a blind
    rubric look unbreakable.
    """
    if not evasions:
        raise AssayError(
            "attack with no evasions always reports HELD, for every rubric "
            "ever written. Pass evasions.")
    if max_combined < 1:
        raise AssayError("max_combined must be at least 1")
    ids = [e.id for e in evasions]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        raise AssayError(
            f"evasion ids are not unique: {dups}. The report names evasions "
            "by id, so a duplicate makes 'slips past via X' ambiguous.")

    defective = [s for s in specimens.specimens if s.defects]
    caught: list[tuple[Specimen, tuple[str, ...]]] = []
    uncaught = 0
    for s in defective:
        firing = tuple(c.id for c in rubric.checkpoints
                       if c.targets & s.defects and c.fires(s))
        if firing:
            caught.append((s, firing))
        else:
            uncaught += 1

    # A mutated transcript that is byte-identical to a DIFFERENT specimen has
    # that specimen's defects, not the original's, by the pack's own ground
    # truth. If the match is clean, the "evasion" deleted the defect and is a
    # repair. Declared preservation does not override a label the material
    # already carries. Found by a constructed probe: an evasion rewriting the
    # defect into the clean twin's wording was counted as a win.
    by_text = {sp.transcript: sp for sp in specimens.specimens}

    evaded: list[Evaded] = []
    ceiling = min(max_combined, len(evasions))
    for s, firing in caught:
        usable = [e for e in evasions if e.safe_for(s)]
        hit = None
        for size in range(1, min(ceiling, len(usable)) + 1):
            for combo in combinations(usable, size):
                text = s.transcript
                for e in combo:
                    text = e.apply(text)
                    if not isinstance(text, str):
                        raise AssayError(
                            f"evasion {e.id!r} returned {type(text).__name__}, "
                            "not a transcript. It cannot have hidden anything.")
                if text == s.transcript:
                    # A combination that changes nothing cannot be an evasion,
                    # and silently counting it would be a free win.
                    continue
                twin = by_text.get(text)
                if twin is not None and twin.defects != s.defects:
                    continue   # landed on material labelled otherwise: a repair
                mutated = Specimen(s.id, text, s.defects, s.note)
                still = [c.id for c in rubric.checkpoints
                         if c.targets & s.defects and c.fires(mutated)]
                if not still:
                    hit = Evaded(s.id, tuple(sorted(s.defects)), firing,
                                 tuple(e.id for e in combo), text)
                    break
            if hit:
                break
        if hit:
            evaded.append(hit)

    return AttackReport(
        rubric_id=rubric.id,
        specimen_set_id=specimens.id,
        n_caught=len(caught),
        n_uncaught=uncaught,
        evaded=tuple(evaded),
        searched_up_to=ceiling,
        exhaustive=ceiling >= len(evasions),
    )


def paraphrase(eid: str, old: str, new: str, description: str = "",
               unsafe_for: frozenset[str] = frozenset()) -> Evasion:
    """Build a domain paraphrase evasion.

    Rewording is only defect-preserving if the author says so, which is why
    this lives here as a constructor rather than in the generic battery. The
    claim belongs to whoever writes the pack.
    """
    if old == new:
        raise AssayError(
            f"paraphrase {eid!r} rewrites {old!r} to itself, so it can never "
            "evade anything and would quietly inflate a HELD verdict.")
    return Evasion(eid, description or f"Reword {old!r} as {new!r}.",
                   _in_reply(lambda r: r.replace(old, new)), unsafe_for)


__all__ = ["AttackReport", "Evaded", "Evasion", "GENERIC_EVASIONS", "attack",
           "paraphrase"]
