"""Generated ground truth is only worth more than labelled ground truth if the
generator refuses to produce a lie. These pin the refusals.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (AssayError, Base, Checkpoint, Injection, Pack, Rubric,
                       append_to_reply, defect_classes, prepend_to_reply,
                       replace_in_reply, run)

BASES = [
    Base("ask_fee", "REQUEST: What is the change fee?\nREPLY: As of 2026-09-01 the fee is $0."),
    Base("ask_book", "REQUEST: Book the 9am to Denver.\nREPLY: Before I book, do you have a seat preference?"),
]

INVENT = Injection("invent_seat", "wrong_versus_absent",
                   replace_in_reply("Before I book, do you have a seat preference?",
                                    "Booking confirmed. I selected a window seat in row 14."),
                   applies_to=frozenset({"ask_book"}))
STALE = Injection("strip_anchor", "confident_staleness",
                  replace_in_reply("As of 2026-09-01 the fee is $0.",
                                   "The fee is $200."),
                  applies_to=frozenset({"ask_fee"}))


def test_a_pack_builds_clean_and_defective_material_with_provenance():
    built = Pack("flight", BASES, [INVENT, STALE]).build()
    ids = {s.id for s in built.specimens}
    assert {"ask_fee", "ask_book", "ask_book__invent_seat",
            "ask_fee__strip_anchor"} == ids
    gen = next(s for s in built.specimens if s.id == "ask_book__invent_seat")
    assert gen.defects == defect_classes("wrong_versus_absent")
    assert gen.note == "generated: base=ask_book injection=invent_seat"
    assert built.present_defects == defect_classes("wrong_versus_absent",
                                                   "confident_staleness")


def test_a_no_op_injection_is_refused():
    """THE one. A specimen labelled defective but byte-identical to clean
    material makes every rubric score perfectly on it, with no symptom."""
    noop = Injection("noop", "rot", replace_in_reply("nothing here", "also absent"))
    with pytest.raises(AssayError, match="did not change base"):
        Pack("p", BASES, [noop]).build()


def test_an_injection_applying_to_an_absent_base_is_refused_at_construction():
    """Caught by __post_init__, which is why build() carries no second check
    for it. A guard that cannot fire is decoration."""
    orphan = Injection("orphan", "rot", append_to_reply("x"),
                       applies_to=frozenset({"ask_fee"}))
    with pytest.raises(AssayError, match="do not exist"):
        Pack("p", [BASES[1]], [orphan])


def test_an_injection_naming_an_unknown_base_is_refused():
    ghost = Injection("ghost", "rot", append_to_reply("x"),
                      applies_to=frozenset({"no_such_base"}))
    with pytest.raises(AssayError, match="do not exist"):
        Pack("p", BASES, [ghost])


def test_a_pack_with_no_injections_is_refused():
    with pytest.raises(AssayError, match="only produce clean material"):
        Pack("p", BASES, [])


def test_building_is_deterministic_and_fingerprinted():
    p = Pack("flight", BASES, [INVENT, STALE])
    a, b = p.build(), p.build()
    assert [s.transcript for s in a.specimens] == [s.transcript for s in b.specimens]
    assert p.fingerprint() == Pack("flight", BASES, [INVENT, STALE]).fingerprint()
    assert p.fingerprint() != Pack("other", BASES, [INVENT, STALE]).fingerprint()


def test_generated_material_actually_drives_an_assay():
    """End to end: a pack builds material, and a rubric assayed against it gets
    a real coverage number rather than a vacuous one."""
    built = Pack("flight", BASES, [INVENT, STALE]).build()
    rubric = Rubric("r", [
        Checkpoint("cp_unanchored", defect_classes("confident_staleness"),
                   lambda t: "$" in t.split("REPLY:")[1] and "as of" not in t.lower()),
        Checkpoint("cp_invented", defect_classes("wrong_versus_absent"),
                   lambda t: "seat" in t.split("REPLY:")[1].lower()
                   and "seat" not in t.split("REPLY:")[0].lower()
                   and "?" not in t.split("REPLY:")[1]),
    ])
    a = run(rubric, built)
    assert a.coverage == 1.0
    assert a.residual == ()
    assert all(c.separation > 0 for c in a.checkpoints)


def test_the_public_pack_agrees_with_the_hand_written_set():
    """Layer 2's whole claim is that constructed ground truth is at least as
    good as labelled ground truth. Both rubrics must score the same against the
    generated pack as against the hand-written material in the example."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
    from flight_rubric import SPECIMENS, naive_v1, written_v2

    from packs.flight_v1 import FLIGHT_V1
    built = FLIGHT_V1.build()

    for rubric in (naive_v1, written_v2):
        hand, gen = run(rubric, SPECIMENS), run(rubric, built)
        assert hand.coverage == gen.coverage, rubric.id
        assert set(hand.residual) == set(gen.residual), rubric.id
        assert set(hand.decoration) == set(gen.decoration), rubric.id

    assert run(naive_v1, built).coverage == 1 / 3
    assert run(written_v2, built).coverage == 1.0


def test_every_clean_base_is_the_near_miss_of_its_own_injection():
    """A structural property worth keeping: each injection rewrites its clean
    base, so the pack always contains the innocent twin of every defect. That
    is what TAXONOMY.md asks of a specimen set, enforced by construction."""
    from packs.flight_v1 import FLIGHT_V1
    built = FLIGHT_V1.build()
    clean_ids = {s.id for s in built.clean}
    for s in built.specimens:
        if s.is_clean:
            continue
        base_id = s.id.split("__")[0]
        assert base_id in clean_ids, f"{s.id} has no clean counterpart"
