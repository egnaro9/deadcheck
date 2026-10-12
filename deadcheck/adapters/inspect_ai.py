"""Load an Inspect AI deterministic scorer as a Rubric, with its material.

Inspect (UK AISI) ships three scorers a second person can apply without a
model. Each is reproduced here from the source in `inspect_ai/scorer/`, and
none is fixed:

  pattern(regex)   re.search(regex, completion, IGNORECASE); the first
                   capture group (the whole match when there are none) must
                   EQUAL a target, lower-cased. No match at all is INCORRECT
                   too, and upstream records why: `invalid_response_format`,
                   an instruction-following failure charged to the model.
  includes()       casefold both, then `target in completion`. A SUBSTRING.
  match()          strip whitespace, casefold, strip punctuation, then
                   `completion.endswith(target)`; location="end" is the
                   default, "begin", "any" and "exact" are the others.
                   numeric=True takes a separate branch, not reproduced.

The subject is BoolQ as `inspect_evals` ships it: `pattern(BOOLQ_PATTERN)`
over a template that ends "answer ... with either Yes or No. Include nothing
else in your response." `includes()` is what infinite_bench and cybench use;
`match()` is the library's default. Run over the SAME material, the three
disagree, and the disagreement is the finding:

  "yes."   "**Yes**\\n"   " YES"      all three accept
  "Yes, because the passage says so."  pattern REJECTS, match(end) REJECTS,
                                       includes accepts
  "The passage supports it. Yes."      pattern REJECTS, match(end) accepts,
                                       includes accepts
  "No. The passage does not support Yes."
                                       pattern fires, includes ACCEPTS,
                                       match(end) ACCEPTS

The two REJECTS rows are upstream's stated choice: the template said to
include nothing else, and the scorer names the reason in its Score. The last
row is nobody's choice. A wrong answer that MENTIONS the right one passes two
of the three scorers, one by substring and one because the sentence happens
to end with the word.

Contrast with adapters/openai_evals.py. evals' Match is a raw prefix with no
strip, so " 1" fails and "10" passes for ideal "1". Inspect's `pattern` is
anchored at both ends and skips leading non-word characters, so neither
failure exists here; its `includes` carries the substring form of the second
("Yesterday" contains "yes").

ONE CHECKPOINT PER SCORER, ONE RUBRIC PER SCORER. A rubric's coverage is its
best checkpoint, so bundling three predicates into one rubric would let the
tight one hide the loose ones. Classes are assertion-shaped (see
adapters/promptfoo.py for why): a Yes/No target can only express
`required_content_absent`.
"""

from __future__ import annotations

import re
import string
from collections.abc import Callable, Iterable

from ..model import AssayError, Checkpoint, Rubric, Specimen, SpecimenSet, defect_classes
from .promptfoo import REQUIRED_ABSENT

SCORERS = ("pattern", "includes", "match")
LOCATIONS = ("begin", "end", "any", "exact")

# inspect_evals/boolq/boolq.py, verbatim: the scorer and the prompt template.
BOOLQ_PATTERN = r"\A[\W_]*(Yes|No)[\W_]*\Z"
BOOLQ_TEMPLATE = (
    "\nGiven a passage, answer the subsequent question with either Yes or No. "
    "Include nothing else in your response.\n\nPassage: {passage}\n\n"
    "Question: {question}\n")


def _strip_punctuation(s: str) -> str:
    # inspect_ai/_util/text.py strip_punctuation, verbatim
    return s.strip(string.whitespace + string.punctuation)


def pattern_correct(regex: str, completion: str, targets: Iterable[str],
                    ignore_case: bool = True, match_all: bool = False) -> bool:
    """`pattern()`'s verdict, from inspect_ai/scorer/_pattern.py.

    Upstream lower-cases here (`match_target`) where the other two scorers
    casefold; reproduced as written.
    """
    m = re.search(regex, completion, re.IGNORECASE if ignore_case else 0)
    if not m:
        return False            # upstream: INCORRECT, reason invalid_response_format
    groups = m.groups() or (m.group(0),)
    tg = [t.lower() for t in targets] if ignore_case else list(targets)

    def hit(s: str) -> bool:
        return (s.lower() if ignore_case else s) in tg

    strs = [g for g in groups if isinstance(g, str)]
    if match_all:
        # every captured group must be a target, and at least one must exist
        return bool(strs) and all(hit(g) for g in strs)
    return any(hit(g) for g in strs)


def includes_correct(completion: str, targets: Iterable[str],
                     ignore_case: bool = True) -> bool:
    """`includes()`'s verdict, from inspect_ai/scorer/_match.py."""
    for target in targets:
        value = completion
        if ignore_case:
            value, target = value.casefold(), target.casefold()
        if target in value:
            return True
    return False


def match_correct(completion: str, targets: Iterable[str], location: str = "end",
                  ignore_case: bool = True, ignore_punctuation: bool = True) -> bool:
    """`match()`'s verdict for a TEXT target: inspect_ai/scorer/_common.py
    match_str with numeric=False. The numeric branch is not reproduced."""
    if location not in LOCATIONS:
        raise AssayError(f"match() location must be one of {LOCATIONS}, "
                         f"not {location!r}")
    for target in targets:
        v, t = completion.strip(), target.strip()
        if ignore_case:
            v, t = v.casefold(), t.casefold()
        if ignore_punctuation:
            v, t = _strip_punctuation(v), _strip_punctuation(t)
        if location == "begin":
            ok = v.startswith(t)
        elif location == "end":
            ok = v.endswith(t)
        elif location == "exact":
            ok = v == t
        else:
            ok = t in v
        if ok:
            return True
    return False


def _targets(sample: dict) -> list[str]:
    t = sample["target"]
    return [str(x) for x in t] if isinstance(t, (list, tuple)) else [str(t)]


def _input(sample: dict) -> str:
    inp = sample["input"]
    if isinstance(inp, str):
        return inp
    users = [m.get("content", "") for m in inp if m.get("role") == "user"]
    if not users:
        raise AssayError("sample has no user message to scope a checkpoint to")
    return users[-1]


def _request(t: str) -> str:
    return t.split("REPLY:", 1)[0]


def _reply(t: str) -> str:
    # NOT stripped here: each scorer strips, or does not, exactly as upstream.
    return t.split("REPLY:", 1)[1] if "REPLY:" in t else t


def transcript(sample: dict, completion: str) -> str:
    return f"REQUEST: {_input(sample)}\nREPLY:{completion}"


def from_samples(samples: Iterable[dict], scorer: str = "pattern", *,
                 regex: str | None = None, location: str = "end",
                 ignore_case: bool = True, match_all: bool = False,
                 limit: int | None = None, rubric_id: str | None = None) -> Rubric:
    """ONE checkpoint: find the sample by its input text, then fire when the
    chosen scorer would mark the completion INCORRECT. A transcript whose
    request matches no sample cannot be judged and does not fire."""
    if scorer not in SCORERS:
        raise AssayError(f"no Inspect scorer named {scorer!r}; one of {SCORERS}")
    if scorer == "pattern" and not regex:
        raise AssayError("pattern() needs its regex; BoolQ's is BOOLQ_PATTERN")
    rows = list(samples)[: limit] if limit else list(samples)
    if not rows:
        raise AssayError("no samples")
    by_request = {_input(s): _targets(s) for s in rows}

    verdict: Callable[[str, list[str]], bool]
    if scorer == "pattern":
        verdict = lambda c, tg: pattern_correct(regex, c, tg, ignore_case, match_all)
        how = (f"pattern({regex!r}): re.search, then the capture group must "
               f"equal the target{'' if ignore_case else ', case-sensitive'}")
    elif scorer == "includes":
        verdict = lambda c, tg: includes_correct(c, tg, ignore_case)
        how = ("includes(): the target is a SUBSTRING of the completion"
               + (", case-folded" if ignore_case else ""))
    else:
        verdict = lambda c, tg: match_correct(c, tg, location, ignore_case)
        how = (f"match(location={location!r}): strip, casefold, strip "
               f"punctuation, then compare at the {location}")

    def fires(t: str) -> bool:
        tg = next((v for k, v in by_request.items() if k in _request(t)), None)
        if tg is None:
            return False          # not one of this eval's samples
        return not verdict(_reply(t), tg)

    rid = rubric_id or f"inspect_{scorer}"
    cp = Checkpoint(rid, defect_classes(REQUIRED_ABSENT), fires,
                    f"Inspect {how}; over {len(rows)} samples, as upstream")
    return Rubric(rid, [cp], f"adapted from {len(rows)} Inspect samples as one "
                  f"parameterised {scorer}() checkpoint", kind="subject")


def material(samples: Iterable[dict], limit: int | None = None,
             set_id: str = "inspect_boolq") -> SpecimenSet:
    """Seven completions per sample. Five are correct by intent, in forms a
    model actually produces; two are wrong. The notes say which scorer
    deviates on each, and tests/test_adapter_inspect_ai.py pins every one of
    those claims to the code, because a note is prose and prose cannot fail."""
    rows = list(samples)[: limit] if limit else list(samples)
    labels = sorted({_targets(s)[0] for s in rows})
    specs: list[Specimen] = []
    for i, s in enumerate(rows):
        t = _targets(s)[0]
        o = next((l for l in labels if l != t), t + "x")
        specs += [
            Specimen(f"s{i}_target", transcript(s, t), note="the target, verbatim"),
            Specimen(f"s{i}_target_lower_punct", transcript(s, t.lower() + "."),
                     note="correct by intent; all three accept"),
            Specimen(f"s{i}_target_bold", transcript(s, f"**{t}**\n"),
                     note="correct by intent, markdown bold and a newline; "
                          "all three accept"),
            Specimen(f"s{i}_target_explained",
                     transcript(s, f"{t}, because the passage says so."),
                     note="correct by intent; pattern REJECTS (format), "
                          "match(end) REJECTS, includes accepts"),
            Specimen(f"s{i}_target_at_end",
                     transcript(s, f"The passage supports it. {t}."),
                     note="correct by intent; pattern REJECTS (format), "
                          "match(end) accepts, includes accepts"),
            Specimen(f"s{i}_wrong", transcript(s, o), frozenset({REQUIRED_ABSENT}),
                     note="the other label"),
            Specimen(f"s{i}_wrong_mentions_target",
                     transcript(s, f"{o}. The passage does not support {t}."),
                     frozenset({REQUIRED_ABSENT}),
                     note="wrong, and the sentence ends with the right word; "
                          "pattern fires, includes ACCEPTS, match(end) ACCEPTS"),
        ]
    return SpecimenSet(set_id, specs)


def record_to_sample(record: dict) -> dict:
    """inspect_evals/boolq/boolq.py record_to_sample, minus the stable id."""
    target = "Yes" if record["answer"] else "No"
    return {"input": BOOLQ_TEMPLATE.format(passage=record["passage"],
                                           question=record["question"]),
            "target": target}


__all__ = ["BOOLQ_PATTERN", "BOOLQ_TEMPLATE", "LOCATIONS", "SCORERS",
           "from_samples", "includes_correct", "match_correct", "material",
           "pattern_correct", "record_to_sample", "transcript"]
