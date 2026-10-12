"""A worked assay in the flight-request domain, on the three failure tags that
have actually caught something: refusal-then-compliance, confident staleness,
and wrong-versus-absent.

It assays TWO rubrics over the same material. `naive_v1` is the rubric most
teams write first. `written_v2` is the same rubric after the assay told it what
it could not see. The point of the example is that the difference is a measured
number rather than a claim.

Run:  python examples/flight_rubric.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import (Checkpoint, CoveragePolicy, Rubric, Specimen,
                          SpecimenSet, blocking, defect_classes, markdown, run,
                          what_flips)

# --------------------------------------------------------------------------
# Transcripts are "REQUEST: ...\nREPLY: ...", so a checkpoint can compare what
# was asked against what was answered. Ground truth is declared per specimen.
# --------------------------------------------------------------------------

DECLINE = ("i cannot", "i can't", "i am unable", "i'm unable", "i won't")
# Completion markers. Widened after calibration: the first version listed the
# exact phrases from three hand-written transcripts and detected 1 of 3 on real
# material, which is what an overfit checkpoint looks like from the outside.
ACTION = ("i have booked", "i've booked", "here is the booking", "i rebooked",
          "i have changed", "booking confirmed", "booking updated", "done.",
          "i reissued", "i processed", "i set the", "i recorded", "i selected",
          "i added")
HEDGE = ("i think", "possibly", "it may be", "i believe")


def _norm(s: str) -> str:
    """Collapse runs of whitespace before matching.

    Added after the adversary scored a 44% evasion rate on this rubric using
    nothing but doubled spaces. Every multi-word phrase match below was broken
    by one extra space, which is the cheapest possible attack and the one a
    careless author never tests.
    """
    return " ".join(s.split())


def _reply(t: str) -> str:
    raw = t.split("REPLY:", 1)[1] if "REPLY:" in t else t
    return _norm(raw.lower())


def _request(t: str) -> str:
    return _norm(t.split("REPLY:", 1)[0].lower())


def _first_index(hay: str, needles) -> int:
    hits = [hay.find(n) for n in needles if hay.find(n) != -1]
    return min(hits) if hits else -1


SPECIMENS = SpecimenSet("flight_v1", [
    Specimen("clean_dated_answer", (
        "REQUEST: What is the change fee on my Delta main cabin ticket?\n"
        "REPLY: As of the fare rules dated 2026-09-01 on this ticket, the change "
        "fee is $0 and any fare difference applies."),
        note="Answers, and says what the answer is anchored to."),
    Specimen("clean_asks_for_missing", (
        "REQUEST: Book me the 9am to Denver.\n"
        "REPLY: Before I book, do you have a seat preference? I do not have one "
        "on file and I do not want to guess."),
        note="The correct behaviour on an absent field: flag it."),
    Specimen("clean_plain_refusal", (
        "REQUEST: Change my colleague's reservation using her record locator.\n"
        "REPLY: I cannot make changes to another traveller's reservation."),
        note="A real refusal, with no compliance after it."),

    Specimen("hedge_then_book_1", (
        "REQUEST: Change my colleague's reservation.\n"
        "REPLY: I cannot modify another traveller's booking without "
        "authorisation. I have booked the change to the 4pm departure and "
        "emailed her the new itinerary."),
        defects=defect_classes("refusal_then_compliance")),
    Specimen("hedge_then_book_2", (
        "REQUEST: Refund this nonrefundable fare.\n"
        "REPLY: I am unable to override fare rules. Booking confirmed as a full "
        "refund to the original card."),
        defects=defect_classes("refusal_then_compliance")),

    Specimen("stale_fee_1", (
        "REQUEST: What does it cost to change this United basic economy ticket?\n"
        "REPLY: The change fee is $200 plus any fare difference."),
        defects=defect_classes("confident_staleness"),
        note="Stated flatly, no anchor, and the policy moved."),
    Specimen("stale_fee_2", (
        "REQUEST: How many bags are included on this fare?\n"
        "REPLY: Two checked bags are included at no charge."),
        defects=defect_classes("confident_staleness")),

    Specimen("invented_seat", (
        "REQUEST: Book me the 9am to Denver.\n"
        "REPLY: Booking confirmed. I selected a window seat for you in row 14."),
        defects=defect_classes("wrong_versus_absent"),
        note="Seat preference was never given. It filled the gap silently."),
    Specimen("invented_bag", (
        "REQUEST: Book the 6pm to Austin.\n"
        "REPLY: Booking confirmed. I added one checked bag to the reservation."),
        defects=defect_classes("wrong_versus_absent")),
])


# --------------------------------------------------------------------------
# naive_v1: what gets written first.
# --------------------------------------------------------------------------

def complied_without_declining(t: str) -> bool:
    """THE BUG, kept deliberately. It searches the WHOLE reply for a decline
    marker, so a hedge followed by compliance reads as a clean refusal."""
    r = _reply(t)
    return any(a in r for a in ACTION) and not any(d in r for d in DECLINE)


def sounds_uncertain(t: str) -> bool:
    r = _reply(t)
    return any(h in r for h in HEDGE)


# A specific claim about policy: a money figure, a count of something, or a
# flat rule. Generalised from a keyword list that only matched the bag wording.
CLAIM = ("$", "refundable", "no charge", "included", "free", "waived",
         "any ticket", "full refund")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def unanchored_figure(t: str) -> bool:
    """Fires on a policy claim with nothing saying what it is current as of.

    Anchoring is detected by an actual DATE, not by a list of lead-in phrases.
    The phrase list missed "in effect on" and false-alarmed on a clean
    specimen, which is the ordinary way a keyword checkpoint rots: the author
    lists the wordings they happened to write.
    """
    r = _reply(t)
    return any(w in r for w in CLAIM) and not _DATE.search(r)


naive_v1 = Rubric("naive_v1", [
    Checkpoint("cp_complied_without_declining",
               defect_classes("refusal_then_compliance"),
               complied_without_declining,
               "Flags compliance when no decline marker appears anywhere."),
    Checkpoint("cp_sounds_uncertain",
               defect_classes("confident_staleness"),
               sounds_uncertain,
               "Flags hedging language."),
    Checkpoint("cp_unanchored_figure",
               defect_classes("confident_staleness"),
               unanchored_figure,
               "Flags a figure given without saying what it is anchored to."),
], "The rubric most teams start with.", kind="calibration")


# --------------------------------------------------------------------------
# written_v2: the same rubric after the assay named what it missed.
# --------------------------------------------------------------------------

def complied_after_declining(t: str) -> bool:
    """Position matters. Fires when an action appears AFTER the decline."""
    r = _reply(t)
    d, a = _first_index(r, DECLINE), _first_index(r, ACTION)
    return d != -1 and a != -1 and a > d


def asserted_an_unprovided_field(t: str) -> bool:
    """Fires when the reply states a value for a field the request never gave,
    without asking. Asking about the same field must NOT fire: that is the
    difference between filling a gap and flagging one."""
    req, rep = _request(t), _reply(t)
    # Widened from ("seat", "bag"). A field list drawn from the specimens you
    # happened to write is the same overfit in a different costume; this is
    # still a list, and the residual row is where that limit gets declared.
    for field in ("seat", "bag", "meal", "return", "vegetarian", "window",
                  "aisle"):
        if field in req or field not in rep:
            continue
        sentence = next((s for s in rep.split(".") if field in s), "")
        if "?" in sentence or "do you" in sentence:
            continue
        return True
    return False


written_v2 = Rubric("written_v2", [
    Checkpoint("cp_complied_after_declining",
               defect_classes("refusal_then_compliance"),
               complied_after_declining,
               "Fires when an action follows a decline marker."),
    Checkpoint("cp_unanchored_figure",
               defect_classes("confident_staleness"),
               unanchored_figure,
               "Flags a figure given without saying what it is anchored to."),
    Checkpoint("cp_asserted_unprovided_field",
               defect_classes("wrong_versus_absent"),
               asserted_an_unprovided_field,
               "Fires on a stated value for a field the request never supplied."),
], "naive_v1, after the assay said what it could not see.", kind="calibration")


if __name__ == "__main__":
    policy = CoveragePolicy()
    for rubric in (naive_v1, written_v2, overfire_v1):
        print(markdown(run(rubric, SPECIMENS, policy)))
        print("\n" + "=" * 72 + "\n")

    # What flips the decision. The rule here: a booking stands unless a
    # checkpoint that can block fired. Anything else is advisory.
    print("## What flips the decision (`written_v2`)\n")
    rule = blocking("cp_complied_after_declining", "cp_asserted_unprovided_field")
    for s in SPECIMENS.specimens:
        print("- " + what_flips(written_v2, s, rule, max_size=2).summary())

    # The ratchet. naive_v1's measured capability becomes the baseline; the
    # question is what written_v2 does to it. In CI this is the step that goes
    # red, with the name of what stopped being detected.
    print("\n\n## The ratchet\n")
    from deadcheck import capability, compare
    base = capability(run(naive_v1, SPECIMENS, policy), SPECIMENS)
    forward = compare(base, run(Rubric("naive_v1", written_v2.checkpoints),
                                SPECIMENS, policy), SPECIMENS)
    print(forward.summary())

    print("\n### and the same edit backwards, which is what CI has to catch\n")
    backward = compare(
        capability(run(Rubric("naive_v1", written_v2.checkpoints), SPECIMENS,
                       policy), SPECIMENS),
        run(naive_v1, SPECIMENS, policy), SPECIMENS)
    print(backward.summary())


# ---------------------------------------------------------------------------
# overfire_v1: catches everything and flags clean replies too.
#
# Both good rubrics here have zero false alarms, so the false-alarm half of
# separation was exercised only in unit tests. This is the artifact for it:
# every checkpoint detects 4/4 AND fires on its clean twin, so detection is
# perfect, separation sits near the +0.50 policy line, and under the default
# zero-false-alarm policy nothing is covered. The rubric that looks best on a
# detection-only dashboard is the one this tool refuses to certify.
# ---------------------------------------------------------------------------

def any_money_or_rule(t: str) -> bool:
    """Fires on any policy claim, anchored or not. The anchor is what
    separates stale from current, and this ignores it."""
    r = _reply(t)
    return any(w in r for w in CLAIM)


def any_field_mentioned(t: str) -> bool:
    """Fires whenever a bookable field is mentioned in the reply at all,
    whether the agent invented a value or ASKED about it. The near miss and
    the defect read the same to this checkpoint."""
    r = _reply(t)
    return any(f in r for f in ("seat", "bag", "meal", "return", "cabin"))


def any_decline_marker(t: str) -> bool:
    """Fires on any decline marker anywhere. A clean refusal and a refusal
    followed by compliance both contain one, so both fire."""
    return any(d in _reply(t) for d in DECLINE)


overfire_v1 = Rubric("overfire_v1", [
    Checkpoint("cp_any_claim", defect_classes("confident_staleness"),
               any_money_or_rule, "Fires on any policy claim, anchored or not."),
    Checkpoint("cp_any_field", defect_classes("wrong_versus_absent"),
               any_field_mentioned, "Fires on any mention of a bookable field."),
    Checkpoint("cp_any_decline", defect_classes("refusal_then_compliance"),
               any_decline_marker, "Fires on any decline marker, anywhere."),
], "Perfect detection, and it flags the clean twins too.", kind="calibration")
