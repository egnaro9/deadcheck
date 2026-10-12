"""Calibration fixtures for layer 8: one rating set per agreement verdict.

Layer 8 scores whether a second person can apply a checkpoint and get the
same answer, and its signature verdict, `misimplemented`, had no known-good
trigger: no fixture in the repo made two humans agree with each other and
disagree with the code. These four sets do, one per verdict, so the agreement
layer has the same kind of calibration battery as the rest of the instrument.

They are fixtures, not findings. The raters are constructed. Their job is to
prove `agree()` can return each verdict, not to say anything about any real
rubric.
"""

from __future__ import annotations

from deadcheck import Checkpoint, Rating, Specimen, SpecimenSet, defect_classes

ROT = "rot"

MATERIAL = SpecimenSet("ratings_material", [
    Specimen("c1", "REQUEST: q?\nREPLY: an ordinary reply."),
    Specimen("c2", "REQUEST: q?\nREPLY: another plain reply."),
    Specimen("c3", "REQUEST: q?\nREPLY: a third clean reply."),
    Specimen("r1", "REQUEST: q?\nREPLY: this one is rotten.", defect_classes(ROT)),
    Specimen("r2", "REQUEST: q?\nREPLY: rotten through.", defect_classes(ROT)),
    Specimen("r3", "REQUEST: q?\nREPLY: plainly rotten.", defect_classes(ROT)),
])
IDS = tuple(s.id for s in MATERIAL.specimens)
TRUTH = (False, False, False, True, True, True)

# The PROSE says one thing; the PREDICATE does the opposite. A rater reading
# the description fires on rotten replies. The code fires on clean ones.
MISIMPLEMENTED_CP = Checkpoint(
    "cp_misimplemented", defect_classes(ROT),
    lambda t: "rotten" not in t,
    "Fires when the reply is rotten.")

SOUND_CP = Checkpoint("cp_sound", defect_classes(ROT),
                      lambda t: "rotten" in t,
                      "Fires when the reply is rotten.")


def _rate(rater: str, cp: str, verdicts) -> list[Rating]:
    return [Rating(rater, cp, sid, v) for sid, v in zip(IDS, verdicts)]


# One set per verdict. Each is the minimal shape that produces it.
FIXTURES = {
    "sound": (SOUND_CP,
              _rate("ana", "cp_sound", TRUTH) + _rate("ben", "cp_sound", TRUTH)),
    "misimplemented": (MISIMPLEMENTED_CP,
                       _rate("ana", "cp_misimplemented", TRUTH)
                       + _rate("ben", "cp_misimplemented", TRUTH)),
    "ambiguous": (SOUND_CP,
                  _rate("ana", "cp_sound", TRUTH)
                  + _rate("ben", "cp_sound", (False, True, False, True, False, True))),
    "inconclusive": (SOUND_CP,
                     _rate("ana", "cp_sound", (True,) * 6)
                     + _rate("ben", "cp_sound", (True,) * 6)),
}


if __name__ == "__main__":
    from deadcheck import agree

    for want, (cp, ratings) in FIXTURES.items():
        res = agree(cp, MATERIAL, ratings)
        mark = "ok " if res.verdict == want else "BUG"
        print(f"[{mark}] expected {want:<14} got {res.verdict}")
