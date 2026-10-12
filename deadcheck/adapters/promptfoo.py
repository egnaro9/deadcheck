"""Load a promptfoo config's DETERMINISTIC assertions as a Rubric.

The core stays zero-dependency: `from_config` takes an already-parsed dict.
`load` imports yaml lazily and says what to install if it is absent.

POLARITY. A promptfoo assertion is a PASS condition; a deadcheck checkpoint
FIRES on a defect. So `contains X` becomes a checkpoint that fires when X is
absent from the reply, and `not-contains Y` fires when Y is present.

CLASSES ARE ASSERTION-SHAPED, NOT FAILURE-SHAPED. A promptfoo assertion names
an expected string, not a defect class, so this assigns one by assertion type
and says so. These classes fail TAXONOMY.md's first bar (name the incident) on
purpose: they are what a contains-style rubric actually targets, and labelling
that honestly is the finding, not a limitation of the adapter.

LLM-graded assertions (`llm-rubric`, `promptfoo:redteam:*`, `similar`,
`model-graded-*`) are skipped and counted, never silently dropped. A rubric is
only measurable here if a second person could apply it without a model.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..model import AssayError, Checkpoint, Rubric, defect_classes

REQUIRED_ABSENT = "required_content_absent"
FORBIDDEN_PRESENT = "forbidden_content_present"
PATTERN_ABSENT = "required_pattern_absent"
PATTERN_PRESENT = "forbidden_pattern_present"

DETERMINISTIC = {
    "contains": REQUIRED_ABSENT, "icontains": REQUIRED_ABSENT,
    "contains-any": REQUIRED_ABSENT, "icontains-any": REQUIRED_ABSENT,
    "contains-all": REQUIRED_ABSENT, "icontains-all": REQUIRED_ABSENT,
    "starts-with": REQUIRED_ABSENT, "equals": REQUIRED_ABSENT,
    "not-contains": FORBIDDEN_PRESENT, "not-icontains": FORBIDDEN_PRESENT,
    "regex": PATTERN_ABSENT, "not-regex": PATTERN_PRESENT,
}


def _reply(t: str) -> str:
    """promptfoo asserts over the model OUTPUT; deadcheck transcripts carry the
    request too, so predicates run over the REPLY section when one exists."""
    return t.split("REPLY:", 1)[1] if "REPLY:" in t else t


def _slug(s: str, n: int = 28) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")
    return (s or "x")[:n].rstrip("_")


def _predicate(kind: str, value):
    vals = value if isinstance(value, list) else [value]
    strs = [str(v) for v in vals]
    low = [v.lower() for v in strs]
    if kind == "contains":
        return lambda t: strs[0] not in _reply(t)
    if kind == "icontains":
        return lambda t: low[0] not in _reply(t).lower()
    if kind in ("contains-any",):
        return lambda t: not any(v in _reply(t) for v in strs)
    if kind in ("icontains-any",):
        return lambda t: not any(v in _reply(t).lower() for v in low)
    if kind in ("contains-all",):
        return lambda t: not all(v in _reply(t) for v in strs)
    if kind in ("icontains-all",):
        return lambda t: not all(v in _reply(t).lower() for v in low)
    if kind == "starts-with":
        return lambda t: not _reply(t).lstrip().startswith(strs[0])
    if kind == "equals":
        return lambda t: _reply(t).strip() != strs[0].strip()
    if kind == "not-contains":
        return lambda t: strs[0] in _reply(t)
    if kind == "not-icontains":
        return lambda t: low[0] in _reply(t).lower()
    if kind == "regex":
        rx = re.compile(strs[0])
        return lambda t: rx.search(_reply(t)) is None
    if kind == "not-regex":
        rx = re.compile(strs[0])
        return lambda t: rx.search(_reply(t)) is not None
    raise AssayError(f"no predicate for assertion type {kind!r}")


def from_config(cfg: dict, tests: Iterable[int] | None = None,
                rubric_id: str = "promptfoo") -> tuple[Rubric, dict]:
    """Build a Rubric from a parsed promptfoo config.

    Returns (rubric, report). `report["skipped"]` lists every assertion that
    was NOT deterministic, by test and type, so what the rubric leaves out is
    visible rather than quietly dropped.
    """
    all_tests = cfg.get("tests") or []
    picked = list(tests) if tests is not None else list(range(len(all_tests)))
    checkpoints: list[Checkpoint] = []
    skipped: list[dict] = []
    seen: set[str] = set()
    for i in picked:
        t = all_tests[i]
        for a in t.get("assert") or []:
            kind = a.get("type")
            if kind not in DETERMINISTIC:
                skipped.append({"test": i, "type": kind})
                continue
            cid = f"t{i}_{_slug(kind)}_{_slug(a.get('value'))}"
            n = 2
            while cid in seen:
                cid = f"{cid}_{n}"
                n += 1
            seen.add(cid)
            checkpoints.append(Checkpoint(
                cid, defect_classes(DETERMINISTIC[kind]),
                _predicate(kind, a.get("value")),
                f"promptfoo test {i}: {kind} {a.get('value')!r}"))
    if not checkpoints:
        raise AssayError(
            "the selected promptfoo tests carry no deterministic assertions. "
            f"Skipped {len(skipped)} LLM-graded or structural assertion(s); a "
            "rubric a second person cannot apply without a model is not "
            "measurable here.")
    return Rubric(rubric_id, checkpoints,
                  f"adapted from a promptfoo config, tests {picked}",
                  kind="subject"), \
        {"checkpoints": len(checkpoints), "skipped": skipped}


def load(path: str, **kw) -> tuple[Rubric, dict]:
    try:
        import yaml  # optional extra: pip install 'deadcheck[promptfoo]'
    except ImportError as exc:
        raise AssayError(
            "reading a promptfoo YAML needs pyyaml, which deadcheck does not "
            "depend on. Install the extra: pip install 'deadcheck[promptfoo]', "
            "or parse the file yourself and call from_config().") from exc
    with open(path) as fh:
        return from_config(yaml.safe_load(fh), **kw)


__all__ = ["DETERMINISTIC", "FORBIDDEN_PRESENT", "PATTERN_ABSENT",
           "PATTERN_PRESENT", "REQUIRED_ABSENT", "from_config", "load"]
