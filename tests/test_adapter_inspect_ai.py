"""Inspect AI's three deterministic scorers, reproduced exactly, over the one
material they disagree on. Every ACCEPTS and REJECTS the adapter's notes
claim is pinned here by code, because a note is prose and prose cannot fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import AssayError, Specimen, run
from deadcheck.adapters.inspect_ai import (BOOLQ_PATTERN, BOOLQ_TEMPLATE,
                                           from_samples, includes_correct,
                                           match_correct, material,
                                           pattern_correct, record_to_sample,
                                           transcript)

SAMPLES = [
    record_to_sample({"question": "is water wet", "passage": "Water is wet.",
                      "answer": True}),
    record_to_sample({"question": "is fire cold", "passage": "Fire is hot.",
                      "answer": False}),
]
ALL = ("pattern", "includes", "match")


def _rubric(scorer, **kw):
    if scorer == "pattern":
        kw.setdefault("regex", BOOLQ_PATTERN)
    return from_samples(SAMPLES, scorer, **kw)


def _fires(scorer, reply, sample=SAMPLES[0], **kw):
    cp = _rubric(scorer, **kw).checkpoints[0]
    return cp.fires(Specimen("x", transcript(sample, reply)))


def _verdicts(reply):
    return {s: _fires(s, reply) for s in ALL}


def test_the_target_verbatim_passes_all_three():
    assert not any(_verdicts("Yes").values())


def test_case_punctuation_and_surrounding_whitespace_pass_all_three():
    assert not any(_verdicts("yes.").values())
    assert not any(_verdicts(" YES\n").values())


def test_markdown_bold_passes_all_three():
    """`[\\W_]*` eats the asterisks for pattern; match strips punctuation."""
    assert not any(_verdicts("**Yes**\n").values())


def test_an_explained_answer_is_a_format_failure_for_pattern():
    """Upstream's stated choice: the template said include nothing else."""
    v = _verdicts("Yes, because the passage says so.")
    assert v["pattern"]                      # REJECTS, invalid_response_format
    assert v["match"]                        # ends with "so", not "yes"
    assert not v["includes"]


def test_the_answer_at_the_end_passes_match_and_includes_not_pattern():
    v = _verdicts("The passage supports it. Yes.")
    assert v["pattern"]
    assert not v["match"] and not v["includes"]


def test_the_wrong_label_fires_all_three():
    assert all(_verdicts("No").values())


def test_a_wrong_answer_that_ends_with_the_right_word():
    """THE finding. Two of three scorers accept a No that mentions Yes."""
    v = _verdicts("No. The passage does not support Yes.")
    assert v["pattern"]
    assert not v["includes"]                 # substring
    assert not v["match"]                    # endswith


def test_pattern_has_no_prefix_hole_unlike_evals_match():
    """'10' passes evals' Match for '1'. 'Yesterday' does not pass pattern
    for 'Yes': the regex is anchored at both ends. includes still takes it."""
    v = _verdicts("Yesterday")
    assert v["pattern"] and v["match"]
    assert not v["includes"]


def test_a_hedge_fires_pattern_only():
    v = _verdicts("Yes or No")
    assert v["pattern"]
    assert not v["includes"]                 # contains "yes"


def test_an_empty_completion_fires_all_three():
    assert all(_verdicts("").values())


def test_match_locations_differ_on_the_same_completion():
    reply = "Yes, because the passage says so."
    assert not _fires("match", reply, location="begin")
    assert not _fires("match", reply, location="any")
    assert _fires("match", reply, location="end")
    assert _fires("match", reply, location="exact")
    assert not _fires("match", "yes.", location="exact")   # punctuation stripped
    with pytest.raises(AssayError, match="location"):
        match_correct("Yes", ["Yes"], location="middle")


def test_pattern_without_groups_compares_the_whole_match():
    assert pattern_correct(r"Yes|No", "I say Yes", ["Yes"])
    assert not pattern_correct(r"Yes|No", "I say Yes", ["No"])


def test_pattern_match_all_needs_every_group():
    rx = r"(Yes|No).*?(Yes|No)"
    assert pattern_correct(rx, "Yes then No", ["Yes"])                    # first group
    assert not pattern_correct(rx, "Yes then No", ["Yes"], match_all=True)
    assert pattern_correct(rx, "Yes then No", ["Yes", "No"], match_all=True)


def test_pattern_and_includes_honour_case_when_told():
    assert not pattern_correct(BOOLQ_PATTERN, "yes", ["Yes"], ignore_case=False)
    assert pattern_correct(BOOLQ_PATTERN, "yes", ["Yes"])
    assert not includes_correct("yes", ["Yes"], ignore_case=False)


def test_the_target_is_looked_up_per_request():
    for s in ALL:
        assert not _fires(s, "No", sample=SAMPLES[1])
        assert _fires(s, "Yes", sample=SAMPLES[1])


def test_a_transcript_from_no_sample_does_not_fire():
    for s in ALL:
        cp = _rubric(s).checkpoints[0]
        assert not cp.fires(Specimen("a", "REQUEST: something else\nREPLY:Yes"))


def test_one_checkpoint_one_rubric_per_scorer():
    ids = set()
    for s in ALL:
        r = _rubric(s)
        assert len(r.checkpoints) == 1 and r.kind == "subject"
        ids.add(r.id)
    assert len(ids) == 3


def test_refusals():
    with pytest.raises(AssayError, match="no Inspect scorer"):
        from_samples(SAMPLES, "choice")
    with pytest.raises(AssayError, match="regex"):
        from_samples(SAMPLES, "pattern")
    with pytest.raises(AssayError, match="no samples"):
        from_samples([], "includes")


def test_record_to_sample_reproduces_the_boolq_template():
    s = record_to_sample({"question": "q", "passage": "p", "answer": True})
    assert s["input"] == BOOLQ_TEMPLATE.format(passage="p", question="q")
    assert s["input"].startswith("\nGiven a passage, answer")
    assert "Include nothing else" in s["input"]
    assert s["target"] == "Yes"
    assert record_to_sample({"question": "q", "passage": "p",
                             "answer": False})["target"] == "No"


def test_material_has_five_clean_and_two_defective_per_sample():
    mat = material(SAMPLES)
    assert len(mat.specimens) == 14
    assert sum(1 for s in mat.specimens if not s.defects) == 10
    notes = {s.id: s.note for s in mat.specimens}
    assert "ACCEPTS" in notes["s0_wrong_mentions_target"]
    assert "REJECTS" in notes["s0_target_explained"]


def test_the_assay_reports_each_predicate_honestly():
    """The matrix the README quotes, per scorer: (hits, targets, false
    alarms, clean). Change the material and this changes with it."""
    mat = material(SAMPLES)
    want = {"pattern": (4, 4, 4, 10),     # perfect detection, format rejections
            "includes": (2, 4, 0, 10),    # misses every wrong-that-mentions
            "match": (2, 4, 2, 10)}       # misses those, rejects explained
    for scorer, counts in want.items():
        c = run(_rubric(scorer), mat).checkpoints[0]
        got = (c.fired_on_target, c.n_target, c.fired_on_clean, c.n_clean)
        assert got == counts, scorer


def test_a_leading_space_passes_here_and_fails_evals_match():
    """The contrast that justifies a third source: two 'deterministic match'
    scorers, one strips and one does not."""
    assert not any(_verdicts(" Yes").values())
