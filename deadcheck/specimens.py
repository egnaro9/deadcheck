"""Layer 2: build specimen material instead of labelling it.

Hand-labelled ground truth is somebody's judgement wearing a lab coat. The
alternative, borrowed from reference-fleet, is to CONSTRUCT the material: start
from a clean transcript, apply one documented, deterministic injection, and the
resulting specimen carries that defect by construction. Its ground truth is a
fact about how it was made, not an opinion about how it reads.

Every generated specimen records its own provenance (which base, which
injection), so a disagreement about a label is settled by rerunning the
injection rather than by arguing.

THE FAILURE THIS MODULE EXISTS TO REFUSE: an injection that does not change the
transcript produces a "defective" specimen identical to the clean one. Ground
truth is then false, and every rubric on earth scores perfectly against it,
forever, with no symptom. `Pack.build` raises on it. An injection that applies
to nothing is refused for the same reason: it is decoration in generator form.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field

from .model import AssayError, Specimen, SpecimenSet, _check_id


@dataclass(frozen=True)
class Base:
    """Clean material. The thing a defect gets injected into, and also a clean
    specimen in its own right, which is what makes false-alarm rates
    computable without writing clean examples twice."""

    id: str
    transcript: str
    note: str = ""

    def __post_init__(self) -> None:
        _check_id("base", self.id)
        if not self.transcript.strip():
            raise AssayError(f"base {self.id!r} has an empty transcript")


@dataclass(frozen=True)
class Injection:
    """One documented way to break a transcript, and the defect class that
    breaking it introduces.

    `apply` must be deterministic: the same base always yields the same
    specimen. Nothing here draws randomness, because a specimen set that
    changes between runs cannot anchor a ratchet.

    `applies_to` names the bases this injection makes sense for. Leave it empty
    to mean all of them.
    """

    id: str
    defect_class: str
    apply: Callable[[str], str]
    description: str = ""
    applies_to: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _check_id("injection", self.id)
        _check_id("defect class", self.defect_class)
        object.__setattr__(self, "applies_to", frozenset(self.applies_to))


@dataclass(frozen=True)
class Pack:
    """A domain pack: clean bases plus injections, expanded into material.

    Building is deterministic and total. The same pack always produces the same
    SpecimenSet, byte for byte, which is what lets a capability baseline mean
    anything a month later.
    """

    id: str
    bases: tuple[Base, ...]
    injections: tuple[Injection, ...]
    description: str = ""

    def __post_init__(self) -> None:
        _check_id("pack", self.id)
        object.__setattr__(self, "bases", tuple(self.bases))
        object.__setattr__(self, "injections", tuple(self.injections))
        if not self.bases:
            raise AssayError(f"pack {self.id!r} has no bases")
        if not self.injections:
            raise AssayError(f"pack {self.id!r} has no injections, so it can "
                             "only produce clean material")
        for coll, kind in ((self.bases, "base"), (self.injections, "injection")):
            seen: set[str] = set()
            for x in coll:
                if x.id in seen:
                    raise AssayError(f"duplicate {kind} id {x.id!r} in pack "
                                     f"{self.id!r}")
                seen.add(x.id)
        unknown = {b for inj in self.injections for b in inj.applies_to} - {
            b.id for b in self.bases}
        if unknown:
            raise AssayError(
                f"pack {self.id!r}: injections name bases that do not exist: "
                + ", ".join(sorted(unknown)))

    @property
    def declared_classes(self) -> frozenset[str]:
        return frozenset(i.defect_class for i in self.injections)

    def build(self) -> SpecimenSet:
        specimens: list[Specimen] = [
            Specimen(b.id, b.transcript, frozenset(),
                     note=b.note or "clean base")
            for b in self.bases]

        for inj in self.injections:
            targets = [b for b in self.bases
                       if not inj.applies_to or b.id in inj.applies_to]
            # No "targets is empty" guard here on purpose. __post_init__
            # rejects an applies_to naming a base that does not exist, and a
            # pack must have bases, so targets is never empty. A check that
            # cannot fire is the thing this package is named after.
            for b in targets:
                out = inj.apply(b.transcript)
                if out == b.transcript:
                    # THE one that must never pass. A no-op injection makes the
                    # ground truth false and every rubric score perfectly
                    # against it, with no symptom anywhere.
                    raise AssayError(
                        f"injection {inj.id!r} did not change base {b.id!r}. "
                        "The specimen would be labelled defective while being "
                        "byte-identical to clean material, so every rubric "
                        "would score perfectly on it. Narrow applies_to, or "
                        "fix the injection.")
                if not out.strip():
                    raise AssayError(
                        f"injection {inj.id!r} emptied base {b.id!r}")
                specimens.append(Specimen(
                    f"{b.id}__{inj.id}", out,
                    frozenset({inj.defect_class}),
                    note=f"generated: base={b.id} injection={inj.id}"))

        # Likewise no "declared classes all present" check: every injection
        # emits at least one specimen carrying its own class, so it could only
        # ever pass. SpecimenSet's own invariants still apply.
        return SpecimenSet(self.id, specimens)

    def fingerprint(self) -> str:
        """Identity of the PACK DEFINITION, as distinct from the material it
        produces. Two packs with the same fingerprint build the same set."""
        parts = [self.id]
        parts += [f"B:{b.id}:{hashlib.sha256(b.transcript.encode()).hexdigest()[:12]}"
                  for b in sorted(self.bases, key=lambda b: b.id)]
        parts += [f"I:{i.id}:{i.defect_class}:{','.join(sorted(i.applies_to))}"
                  for i in sorted(self.injections, key=lambda i: i.id)]
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


# ------------------------------------------------------------------ helpers
# Small, readable injection constructors. Each returns a deterministic function
# and nothing here consults a clock or a random source.

def prepend_to_reply(text: str) -> Callable[[str], str]:
    """Insert text at the start of the REPLY section."""
    def apply(t: str) -> str:
        if "REPLY:" not in t:
            return t          # build() turns the no-op into a loud error
        head, reply = t.split("REPLY:", 1)
        return f"{head}REPLY:{' ' + text.strip()}{reply}"
    return apply


def append_to_reply(text: str) -> Callable[[str], str]:
    def apply(t: str) -> str:
        return f"{t.rstrip()} {text.strip()}" if t.strip() else t
    return apply


def replace_in_reply(old: str, new: str) -> Callable[[str], str]:
    """Rewrite inside the reply only, so the request stays the control."""
    def apply(t: str) -> str:
        if "REPLY:" not in t:
            return t
        head, reply = t.split("REPLY:", 1)
        return f"{head}REPLY:{reply.replace(old, new)}"
    return apply


__all__ = ["Base", "Injection", "Pack", "append_to_reply", "prepend_to_reply",
           "replace_in_reply"]
