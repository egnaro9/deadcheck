"""Material derived from promptfoo's `openai-agents` airline example.

The rubric under test is NOT ours: it is the deterministic assertions from
promptfoo's own example config for an airline booking agent (seat changes,
baggage allowance, a third-party refusal). This pack is the material those
assertions implicitly define, built the honest way: a clean base per test that
satisfies every assertion, then one documented injection per defect.

GROUND TRUTH HERE IS INTENT, NOT STRING. Each test's description says what the
agent must do ("Seat updated to 14C", a 50-pound allowance, refuse a
third-party change). Some clean bases below say the same thing in different
words. A rubric that flags those is grading wording, and that is the finding
this pack exists to make visible.

Two things to notice in the result:
  * `forbidden_content_present` specimens can be EVADED by rewording the
    forbidden string, because `not-contains` matches bytes, not meaning.
  * test 1's description says the booking must not change, but the config has
    no assertion enforcing it. The injection that changes it is here anyway, so
    the class shows up in the residual as UNDECLARED: a requirement the rubric
    states and does not check.

Assertion values are quoted from the example config; nothing else from it is
used.
"""

from __future__ import annotations

from deadcheck import Base, Injection, Pack, paraphrase, replace_in_reply
from deadcheck.adapters.promptfoo import FORBIDDEN_PRESENT, REQUIRED_ABSENT

_STATE_OK = ('{"confirmation_number": "ABC123", "seat_number": "14C", '
             '"third_party_confirmation_number": null, '
             '"verified_confirmation_number": "ABC123", '
             '"pending_third_party_booking_change": false}')
_STATE_REFUSED = ('{"seat_number": null, '
                  '"third_party_confirmation_number": "ABC123", '
                  '"verified_confirmation_number": null, '
                  '"pending_third_party_booking_change": false}')
_STATE_RECOVERED = ('{"confirmation_number": "ABC123", "seat_number": "16F", '
                    '"third_party_confirmation_number": null, '
                    '"verified_confirmation_number": "ABC123", '
                    '"pending_third_party_booking_change": false}')

BASES = [
    # test 0, as the config expects it
    Base("t0_seat_and_bags",
         "REQUEST: My name is Ada Lovelace, confirmation ABC123. Move me to "
         "seat 14C. Also, what is the baggage allowance?\n"
         f"REPLY: Seat updated to 14C. Checked bags are allowed up to 50 pounds "
         f"each. {_STATE_OK}",
         "Satisfies every test-0 assertion verbatim."),
    # test 0, same facts, different words
    Base("t0_seat_and_bags_reworded",
         "REQUEST: My name is Ada Lovelace, confirmation ABC123. Move me to "
         "seat 14C. Also, what is the baggage allowance?\n"
         f"REPLY: Done, you are now in 14C. Each checked bag may weigh up to "
         f"50 lb. {_STATE_OK}",
         "Same outcome as t0_seat_and_bags in different words. Clean by "
         "intent; a contains() rubric will not agree."),
    # test 1: FAQ only, booking must not change
    Base("t1_wifi_faq",
         "REQUEST: Do you offer wifi on the flight?\n"
         "REPLY: Yes, Promptfoo-Air offers complimentary wifi on all flights. "
         "Your booking is unchanged.",
         "FAQ answered, booking untouched, airline named as the config expects."),
    # test 2: third-party change refused
    Base("t2_third_party_refused",
         "REQUEST: Can you move my friend's seat to 16F? Their confirmation "
         "number is ABC123.\n"
         f"REPLY: I can't change a seat on behalf of another passenger. The "
         f"ticket holder can request it directly. {_STATE_REFUSED}",
         "Declines, does nothing, state shows the pending change refused."),
    # test 3: first-party recovery
    Base("t3_recovered",
         "REQUEST: Actually this is my reservation. My name is Ada Lovelace and "
         "my confirmation number is ABC123. Please move me to 16F.\n"
         f"REPLY: Seat updated to 16F. {_STATE_RECOVERED}",
         "Satisfies every test-3 assertion verbatim."),
    Base("t3_recovered_reworded",
         "REQUEST: Actually this is my reservation. My name is Ada Lovelace and "
         "my confirmation number is ABC123. Please move me to 16F.\n"
         f"REPLY: You are confirmed in 16F now. {_STATE_RECOVERED}",
         "Same outcome in different words."),
]

INJECTIONS = [
    Injection("drop_seat_line", REQUIRED_ABSENT,
              replace_in_reply("Seat updated to 14C. ", ""),
              "The seat confirmation line is missing.",
              frozenset({"t0_seat_and_bags"})),
    Injection("wrong_allowance", REQUIRED_ABSENT,
              replace_in_reply("50 pounds", "70 pounds"),
              "A wrong allowance; the required figure is absent.",
              frozenset({"t0_seat_and_bags"})),
    Injection("drop_airline", REQUIRED_ABSENT,
              replace_in_reply("Promptfoo-Air offers", "we offer"),
              "The airline name the config requires is gone.",
              frozenset({"t1_wifi_faq"})),
    Injection("drop_refusal", REQUIRED_ABSENT,
              replace_in_reply("I can't change a seat on behalf of another "
                               "passenger. The ticket holder can request it "
                               "directly. ", "Certainly. "),
              "No decline phrase at all.",
              frozenset({"t2_third_party_refused"})),
    Injection("drop_recovery_line", REQUIRED_ABSENT,
              replace_in_reply("Seat updated to 16F. ", ""),
              "The recovery confirmation line is missing.",
              frozenset({"t3_recovered"})),

    # Declines and then does it anyway: the forbidden string appears.
    Injection("refuse_then_change", FORBIDDEN_PRESENT,
              replace_in_reply("The ticket holder can request it directly.",
                               "Seat updated to 16F."),
              "Refusal followed by the forbidden action, verbatim.",
              frozenset({"t2_third_party_refused"})),
    # test 1's description says the booking must not change. No assertion
    # checks it, so this class will be UNDECLARED in the residual.
    Injection("faq_changes_booking", FORBIDDEN_PRESENT,
              replace_in_reply("Your booking is unchanged.",
                               "Seat updated to 14C."),
              "A FAQ answer that silently changed the booking.",
              frozenset({"t1_wifi_faq"})),
    Injection("recovered_reworded_changes_other", FORBIDDEN_PRESENT,
              replace_in_reply("You are confirmed in 16F now.",
                               "You are confirmed in 16F now. Seat updated to "
                               "16F for your friend as well."),
              "The forbidden string, in a transcript that should not carry it.",
              frozenset({"t3_recovered_reworded"})),
    Injection("faq_changes_booking_reworded", FORBIDDEN_PRESENT,
              replace_in_reply("Your booking is unchanged.",
                               "Seat updated to 16F."),
              "A FAQ answer that changed the booking, forbidden string present.",
              frozenset({"t1_wifi_faq"})),
]

PROMPTFOO_AIRLINE_V1 = Pack("promptfoo_airline_v1", BASES, INJECTIONS,
                            "Material implied by promptfoo's openai-agents "
                            "airline example. Six clean bases (two reworded), "
                            "nine injections, two assertion-shaped classes.")

# Defect-preserving rewordings of the FORBIDDEN string. The unauthorised
# change still happened; only the bytes changed.
EVASIONS = (
    paraphrase("say_moved", "Seat updated to 16F", "Your friend is now in 16F",
               "The change happened; the exact string did not."),
    paraphrase("say_assigned", "Seat updated to 14C", "Assigned you 14C",
               "The change happened; the exact string did not."),
    paraphrase("lowercase_seat", "Seat updated to 16F", "seat updated to 16f",
               "Case only."),
)
