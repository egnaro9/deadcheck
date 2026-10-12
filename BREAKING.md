# Break it

This tool certifies that a rubric can fail. The only honest way to trust that
claim is to try to make the tool certify something false. Four targets, in the
order I would try them. A reproducible script in an issue is a finding; a
finding gets a test named after it and credit in the README.

## 1. Forge a bundle the registry accepts

`deadcheck certify` writes a bundle: `assay.json`, two projections, a
`vac.json` manifest with a sha256 for every evidence file and a recomputable
`expect` for every check. `deadcheck registry` re-hashes the evidence,
recomputes every `expect`, requires one scope per check, and rejects a bundle
that measured zero classes.

Produce a bundle whose headline (coverage, floor, residual) is false and which
the registry lists anyway. The last protocol in this family was forged in four
bytes by an outside auditor, so this is not a rhetorical target.

## 2. Score coverage without detecting anything

`packs/flight_v1.py` has three defect classes and twelve clean specimens. Write
a rubric that `deadcheck assay` reports as covering a class, with a checkpoint
that a reviewer reading the predicate would call blind: keyed on specimen
text that is not the defect, on length, on anything the calibration battery in
`deadcheck/calibration.py` does not already probe. The naive probes exist to
set the floor; the target is a predicate that clears the floor without
measuring the class.

## 3. Evade a certified checkpoint while keeping the defect

`deadcheck attack --pack packs.flight_v1:FLIGHT_V1 --rubric
examples.flight_rubric:written_v2` reports 0% evasion for the mechanical
rewrites in `deadcheck/adversary.py`, and the README declares a 44% evasion
rate for domain paraphrase, left unfixed on purpose. Find a rewrite that is
mechanical (no domain knowledge, applies to any transcript), preserves the
defect by the pack's own definition, and silences a covered checkpoint. The
constraint that matters: the defect must survive. Deleting it is a repair.

## 4. Show that an adapter misreads its upstream

`deadcheck/adapters/` claims to reproduce three other tools' scorers verbatim:
promptfoo's deterministic assertions, OpenAI evals' `Match`, and Inspect AI's
`pattern`, `includes` and `match`. Every finding in the README about those
tools rests on that claim. Find an input where an adapter's verdict differs
from the upstream code it cites. One counterexample voids the finding it
supports, which is why this target is listed.

## What does not count

A rubric that is simply bad. The tool is supposed to say so, and does. A
specimen pack that is too easy: that is what `calibrate` is for, and its floor
is printed on every certificate. A paraphrase evasion for `written_v2`: that
number is already published as a limitation.

## How to report

Open an issue with the script, the command you ran, and what the tool said.
Nothing here needs a model, a key, or a network; `pip install -e .` and the
standard library are the whole setup.
