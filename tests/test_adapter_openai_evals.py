"""OpenAI evals' Match, reproduced exactly: a prefix match with no strip and
no case-fold. The three consequences are pinned by name, because an adapter
that quietly fixed any of them would be measuring a rubric nobody runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import AssayError, Specimen, run
from deadcheck.adapters.openai_evals import (from_samples, material,
                                              transcript)

SAMPLES = [
    {"input": [{"role": "system", "content": "reply 1 or 0"},
               {"role": "user", "content": "headline alpha"}], "ideal": "1"},
    {"input": [{"role": "system", "content": "reply 1 or 0"},
               {"role": "user", "content": "headline beta"}], "ideal": "0"},
]


def _fires(reply, sample=SAMPLES[0]):
    cp = from_samples(SAMPLES).checkpoints[0]
    return cp.fires(Specimen("x", transcript(sample, reply)))


def test_the_ideal_verbatim_passes():
    assert not _fires("1")


def test_trailing_punctuation_passes_because_it_is_a_prefix_match():
    assert not _fires("1.")
    assert not _fires("1 because it is sarcastic")


def test_a_leading_space_fails_because_nothing_is_stripped():
    """Correct by intent, rejected by the predicate."""
    assert _fires(" 1")


def test_a_wrong_answer_beginning_with_the_ideal_is_accepted():
    """THE finding. '10' starts with '1', so Match accepts it."""
    assert not _fires("10")
    assert not _fires("1x")


def test_the_wrong_label_fires():
    assert _fires("0")


def test_the_ideal_is_looked_up_per_request():
    cp = from_samples(SAMPLES).checkpoints[0]
    assert not cp.fires(Specimen("a", transcript(SAMPLES[1], "0")))
    assert cp.fires(Specimen("b", transcript(SAMPLES[1], "1")))


def test_a_transcript_from_no_sample_does_not_fire():
    cp = from_samples(SAMPLES).checkpoints[0]
    assert not cp.fires(Specimen("a", "REQUEST: something else\nREPLY:1"))


def test_it_is_one_checkpoint_not_one_per_sample():
    """One per sample diluted every number by the sample count."""
    assert len(from_samples(SAMPLES).checkpoints) == 1
    assert from_samples(SAMPLES).kind == "subject"


def test_material_carries_the_three_consequences_by_label():
    mat = material(SAMPLES)
    notes = {s.id: s.note for s in mat.specimens}
    assert "REJECTS" in notes["s0_ideal_space"] and not mat.specimens[2].defects
    assert "ACCEPTS" in notes["s0_wrong_prefix"] and mat.specimens[4].defects


def test_the_assay_reports_the_predicate_honestly():
    rubric, mat = from_samples(SAMPLES), material(SAMPLES)
    c = run(rubric, mat).checkpoints[0]
    assert c.fired_on_target == 2 and c.n_target == 4      # misses both prefix-wrongs
    assert c.fired_on_clean == 2 and c.n_clean == 6        # flags both leading-space


def test_no_samples_is_refused():
    with pytest.raises(AssayError, match="no samples"):
        from_samples([])
