"""Three Inspect scorers over the same BoolQ material. Read the disagreement.

Material: ten rows of google/boolq (validation split, rows 0 to 9, as served
by the Hugging Face datasets-server on 2026-10-12; CC BY-SA 3.0) in
packs/inspect_boolq_val10.json, mapped through the same record_to_sample as
inspect_evals' boolq task. Seven completions per row: five correct by intent
in forms a model actually produces, two wrong.

The first rubric is BoolQ as shipped. The other two are what the same task
would score with the library's other deterministic scorers at their defaults,
which is how infinite_bench and cybench (includes) and most custom tasks
(match) use them.

Run:  python examples/inspect_boolq.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import run, wilson
from deadcheck.adapters.inspect_ai import (BOOLQ_PATTERN, from_samples,
                                           material, record_to_sample)

FIXTURE = Path(__file__).resolve().parents[1] / "packs" / "inspect_boolq_val10.json"


def _variant(spec_id: str) -> str:
    return spec_id.split("_", 1)[1]


def main() -> int:
    samples = [record_to_sample(r) for r in json.loads(FIXTURE.read_text())]
    mat = material(samples)
    clean = [s for s in mat.specimens if not s.defects]
    wrong = [s for s in mat.specimens if s.defects]
    rubrics = [
        ("pattern, BoolQ as shipped",
         from_samples(samples, "pattern", regex=BOOLQ_PATTERN)),
        ("includes()", from_samples(samples, "includes")),
        ("match(), location=end", from_samples(samples, "match")),
    ]
    print(f"{len(samples)} BoolQ rows, {len(mat.specimens)} specimens "
          f"({len(clean)} correct by intent, {len(wrong)} wrong)\n")
    print(f"{'scorer':<28} {'detects':>8} {'false alarms':>13} {'separation':>11} "
          f"{'95% CI on detection':>20}")
    for label, rubric in rubrics:
        cp = rubric.checkpoints[0]
        c = run(rubric, mat).checkpoints[0]
        lo, hi = wilson(c.fired_on_target, c.n_target)
        print(f"{label:<28} {c.fired_on_target:>3}/{c.n_target:<4} "
              f"{c.fired_on_clean:>5}/{c.n_clean:<7} {c.separation:>+11.2f} "
              f"{f'[{lo:.2f}, {hi:.2f}]':>20}")
        accepts = sorted({_variant(s.id) for s in wrong if not cp.fires(s)})
        rejects = sorted({_variant(s.id) for s in clean if cp.fires(s)})
        print(f"{'':<28} accepts though wrong: {', '.join(accepts) or 'nothing'}")
        print(f"{'':<28} rejects though right: {', '.join(rejects) or 'nothing'}")
    print("\nThe pattern scorer's rejections are upstream's documented choice (the "
          "template says\n\"Include nothing else\"). The other two accepting "
          "wrong_mentions_target is not.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
