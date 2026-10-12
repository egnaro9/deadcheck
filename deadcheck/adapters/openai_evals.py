"""Load an OpenAI `evals` Match-style eval as a Rubric, with its material.

An `evals` sample is {"input": [chat messages], "ideal": str | [str]}, and the
`Match` class judges a completion with evals.api.record_and_check_match, whose
predicate is, verbatim from the source:

    for option in options:
        if not sampled.startswith(option): continue   # prefix match

No strip, no case-fold, a PREFIX. That is reproduced here exactly, because an
adapter that quietly "fixed" it would be measuring a rubric nobody runs. Three
consequences fall out and the material below carries all three:

  "1."  passes for ideal "1"  (prefix)         so punctuation is fine
  " 1"  FAILS for ideal "1"   (no strip)       so a leading space is a miss
  "10"  PASSES for ideal "1"  (prefix)         so a wrong answer that begins
                                               with the right one is accepted

Unlike the promptfoo adapter, this one builds the material too, because a
Match eval's samples ARE the material: each (input, ideal) pair is a clean
base, and a wrong label is the only defect the eval can express.

ONE CHECKPOINT, NOT ONE PER SAMPLE. A Match eval is a single grader
parameterised by sample, so it is adapted as a single checkpoint that looks
the ideal up from the transcript's request. The first draft made one
checkpoint per sample, each scoped to its own request; every number came out
diluted by the sample count, because a checkpoint counts "did not fire" on
the seven samples it was never about. One checkpoint over all the material is
both what the eval is and the only shape the numbers are honest in.

Classes are assertion-shaped (see adapters/promptfoo.py for why): a Match eval
targets one thing, `required_content_absent`, and that it cannot express the
taxonomy at all is part of the finding.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from ..model import AssayError, Checkpoint, Rubric, Specimen, SpecimenSet, defect_classes
from .promptfoo import REQUIRED_ABSENT


def _slug(s: str, n: int = 24) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")
    return (s or "x")[:n].rstrip("_")


def _user_text(sample: dict) -> str:
    msgs = sample.get("input")
    if isinstance(msgs, str):
        return msgs
    users = [m.get("content", "") for m in msgs or [] if m.get("role") == "user"]
    if not users:
        raise AssayError("sample has no user message to scope a checkpoint to")
    return users[-1]


def _request(t: str) -> str:
    return t.split("REPLY:", 1)[0]


def _reply(t: str) -> str:
    # NOT stripped, on purpose: Match does not strip either.
    return t.split("REPLY:", 1)[1] if "REPLY:" in t else t


def transcript(sample: dict, reply: str) -> str:
    return f"REQUEST: {_user_text(sample)}\nREPLY:{reply}"


def from_samples(samples: Iterable[dict], limit: int | None = None,
                rubric_id: str = "openai_evals_match") -> Rubric:
    """ONE checkpoint: find the sample by its request text, then fire when the
    reply does not START WITH any of that sample's ideals, exactly as
    record_and_check_match does. A transcript whose request matches no sample
    cannot be judged and does not fire; it is reported, not guessed at."""
    rows = list(samples)[: limit] if limit else list(samples)
    if not rows:
        raise AssayError("no samples")
    ideals_by_request: dict[str, list[str]] = {}
    for s in rows:
        ideals = s["ideal"] if isinstance(s["ideal"], list) else [s["ideal"]]
        ideals_by_request[_user_text(s)] = [str(x) for x in ideals]

    def fires(t: str) -> bool:
        req = _request(t)
        ideals = next((v for k, v in ideals_by_request.items() if k in req), None)
        if ideals is None:
            return False          # not one of this eval's samples
        return not any(_reply(t).startswith(o) for o in ideals)

    cp = Checkpoint("match_startswith_ideal", defect_classes(REQUIRED_ABSENT),
                    fires, f"evals Match over {len(rows)} samples: the reply "
                    "must START WITH the sample's ideal (prefix, no strip, "
                    "case-sensitive, as upstream)")
    return Rubric(rubric_id, [cp], f"adapted from {len(rows)} OpenAI evals "
                  "Match samples as one parameterised checkpoint",
                  kind="subject")


def material(samples: Iterable[dict], limit: int | None = None,
             set_id: str = "openai_evals_match") -> SpecimenSet:
    """Clean = the ideal as the reply. Also clean BY INTENT: the ideal with
    trailing punctuation, and with a leading space, which Match rejects.
    Defective = a wrong label, and the wrong label that merely BEGINS with
    the right one, which Match accepts."""
    rows = list(samples)[: limit] if limit else list(samples)
    labels = sorted({str(s["ideal"] if not isinstance(s["ideal"], list)
                         else s["ideal"][0]) for s in rows})
    specs: list[Specimen] = []
    for i, s in enumerate(rows):
        ideal = str(s["ideal"] if not isinstance(s["ideal"], list) else s["ideal"][0])
        wrong = next((l for l in labels if l != ideal), ideal + "x")
        specs += [
            Specimen(f"s{i}_ideal", transcript(s, ideal), note="the ideal, verbatim"),
            Specimen(f"s{i}_ideal_punct", transcript(s, ideal + "."),
                     note="correct by intent; Match accepts (prefix)"),
            Specimen(f"s{i}_ideal_space", transcript(s, " " + ideal),
                     note="correct by intent; Match REJECTS (no strip)"),
            Specimen(f"s{i}_wrong", transcript(s, wrong),
                     frozenset({REQUIRED_ABSENT}), note="the other label"),
            Specimen(f"s{i}_wrong_prefix", transcript(s, ideal + "0"),
                     frozenset({REQUIRED_ABSENT}),
                     note="wrong, but begins with the ideal; Match ACCEPTS"),
        ]
    return SpecimenSet(set_id, specs)


def load_jsonl(path: str, limit: int | None = None) -> list[dict]:
    out = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
                if limit and len(out) >= limit:
                    break
    return out


__all__ = ["from_samples", "load_jsonl", "material", "transcript"]
