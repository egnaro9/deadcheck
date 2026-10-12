"""The promptfoo adapter: a rubric nobody here wrote, loaded without a model.
Polarity, scoping and the honest accounting of what was skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import AssayError, Specimen
from deadcheck.adapters.promptfoo import (FORBIDDEN_PRESENT, REQUIRED_ABSENT,
                                          from_config, load)

CFG = {"tests": [
    {"description": "seat", "assert": [
        {"type": "contains", "value": "Seat updated to 14C"},
        {"type": "not-contains", "value": "Seat updated to 16F"},
        {"type": "icontains-any", "value": ["third party", "someone else"]},
        {"type": "llm-rubric", "value": "is polite"},
        {"type": "trajectory:tool-used", "value": ["lookup"]},
    ]},
    {"description": "faq", "assert": [{"type": "regex", "value": r"\d+ pounds"}]},
]}


def _t(reply):
    return f"REQUEST: q\nREPLY: {reply}"


def test_polarity_is_inverted_contains_fires_on_absence():
    rubric, rep = from_config(CFG, tests=[0])
    cp = next(c for c in rubric.checkpoints if "seat_updated_to_14c" in c.id)
    assert cp.targets == frozenset({REQUIRED_ABSENT})
    assert cp.fires(Specimen("a", _t("nothing here")))
    assert not cp.fires(Specimen("b", _t("Seat updated to 14C")))


def test_not_contains_fires_on_presence():
    rubric, _ = from_config(CFG, tests=[0])
    cp = next(c for c in rubric.checkpoints if "not_contains" in c.id)
    assert cp.targets == frozenset({FORBIDDEN_PRESENT})
    assert cp.fires(Specimen("a", _t("ok. Seat updated to 16F")))
    assert not cp.fires(Specimen("b", _t("refused")))


def test_not_contains_is_case_sensitive_like_promptfoo():
    """THE finding. A lowercased forbidden string passes `not-contains`, so a
    refusal followed by 'seat updated to 16f' reads as a clean refusal."""
    rubric, _ = from_config(CFG, tests=[0])
    cp = next(c for c in rubric.checkpoints if "not_contains" in c.id)
    assert not cp.fires(Specimen("a", _t("I can't. seat updated to 16f")))


def test_icontains_any_matches_any_phrase_case_insensitively():
    rubric, _ = from_config(CFG, tests=[0])
    cp = next(c for c in rubric.checkpoints if "icontains_any" in c.id)
    assert not cp.fires(Specimen("a", _t("I cannot act for SOMEONE ELSE.")))
    assert cp.fires(Specimen("b", _t("sure, done")))


def test_predicates_read_the_reply_not_the_request():
    """promptfoo asserts over the output. A required string sitting only in
    the REQUEST must not satisfy the check."""
    rubric, _ = from_config(CFG, tests=[0])
    cp = next(c for c in rubric.checkpoints if "seat_updated_to_14c" in c.id)
    assert cp.fires(Specimen("a", "REQUEST: say Seat updated to 14C\nREPLY: no"))


def test_skipped_assertions_are_counted_not_dropped():
    _, rep = from_config(CFG, tests=[0])
    assert rep["checkpoints"] == 3
    assert {s["type"] for s in rep["skipped"]} == {"llm-rubric", "trajectory:tool-used"}


def test_a_test_with_only_llm_graded_assertions_is_refused():
    only_llm = {"tests": [{"assert": [{"type": "llm-rubric", "value": "nice"}]}]}
    with pytest.raises(AssayError, match="cannot apply without a model"):
        from_config(only_llm)


def test_regex_fires_when_the_pattern_is_absent():
    rubric, _ = from_config(CFG, tests=[1])
    cp = rubric.checkpoints[0]
    assert cp.fires(Specimen("a", _t("fifty lb")))
    assert not cp.fires(Specimen("b", _t("up to 50 pounds")))


def test_load_without_pyyaml_says_what_to_install(monkeypatch, tmp_path):
    import builtins
    real = builtins.__import__

    def no_yaml(name, *a, **k):
        if name == "yaml":
            raise ImportError("no yaml")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_yaml)
    p = tmp_path / "c.yaml"
    p.write_text("tests: []")
    with pytest.raises(AssayError, match=r"deadcheck\[promptfoo\]"):
        load(str(p))


def test_checkpoint_ids_are_unique_even_for_repeated_values():
    cfg = {"tests": [{"assert": [{"type": "contains", "value": "x"},
                                 {"type": "contains", "value": "x"}]}]}
    rubric, _ = from_config(cfg)
    assert len({c.id for c in rubric.checkpoints}) == 2
