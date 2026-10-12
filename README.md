# rubric-assay

**Measure what a rubric can and cannot see.** Bring an eval suite; get back three
numbers and the row everyone else leaves out.

Stdlib-only Python, no dependencies, no model in the loop. The same rubric and
the same specimens always produce the same numbers, so a disagreement about a
score is a disagreement about a predicate.

```
python examples/flight_rubric.py
```

## Why

The eval-tooling market is full of runners and dashboards. They help you run a
suite and look at the results. None of them answers the question every buyer
actually has, which is **"is my rubric any good?"** That gets asserted, never
measured.

A rubric is an instrument. An instrument that cannot fail is not measuring
anything. This measures the instrument.

## The three numbers

**Separation**, per checkpoint. How far it pulls specimens carrying its declared
defect away from clean ones: `detection rate - false alarm rate`. Subtracting
false alarms is the whole trick. A checkpoint that fires on everything has a
perfect detection rate and separation `0.00`, which is the correct verdict on
it. A checkpoint at or below zero is decoration and the report says to cut it.

**Coverage**, per defect class. Which classes *present in the specimen set* some
checkpoint actually catches, under a stated policy. Computed against what the
specimens carry, never against what the rubric claims to target, because a
rubric cannot grade its own ambition.

**Residual.** The classes it misses, by name, plus the classes nothing declares
and the classes no specimen tested. This section prints even when it is empty,
and it prints last. A rubric without a residual is advertising.

## What it looks like

A naive rubric and the same rubric rewritten after the assay named what it could
not see, on the same material:

| rubric | coverage | residual |
|---|--:|---|
| `naive_v1` | 33% | `refusal_then_compliance`, `wrong_versus_absent` |
| `written_v2` | 100% | none in this material |

`naive_v1` also had two checkpoints flagged **DECORATION**: one searched the
whole reply for a decline marker, so a hedge followed by compliance read as a
clean refusal, and one looked for hedging language in a defect class whose
defining trait is that it does not hedge.

## What flips the decision

A separate module, because it scores a different object. The assay scores a
*rubric*. `what_flips` scores a *decision made with* one: given a transcript and
a rule for turning checkpoint outcomes into a verdict, which checkpoints would
have to be wrong for the verdict to reverse?

```python
from rubric_assay import blocking, what_flips

rep = what_flips(rubric, specimen, blocking("cp_complied_after_declining"))
rep.hangs_on_one   # the verdict rests on a single predicate
rep.summary()      # "invented_seat: verdict BLOCKED; flips on 1 checkpoint: {...}"
```

Only **minimal** flip sets are reported, since a superset of a flipping set
trivially flips too and carries no information.

**The two modules are not redundant, and the example proves it.** In
`examples/flight_rubric.py`, `written_v2` scores 100% coverage and still lets
both `confident_staleness` specimens through, because the decision rule does not
let that checkpoint block. Coverage is a property of the rubric. The verdict is
a property of the rule. A perfect rubric wired to a permissive rule is still a
system that approves bad work.

## The guards

This tool measures whether other people's instruments can fail, so it has to
survive the same question. These are enforced, not advised, and each has a test:

- A **checkpoint that declares no targets** is refused. Unscoreable is how
  decoration survives review.
- A **specimen set with no clean specimens** is refused. Without them, a
  checkpoint that fires on everything scores a perfect detection rate.
- A **specimen set with no defective specimens** is refused. Nothing to detect.
- A **predicate that raises** is an error, never a non-fire. Scoring a crash as
  "did not fire" turns a broken checkpoint into a clean bill of health.
- **Claimed but untested** targets are named. A checkpoint whose declared class
  appears in no specimen has an asserted separation, not a measured one.
- **Off-target fires** are counted and printed. A checkpoint that fires mostly
  on defects it does not claim is right by accident.
- A **bounded flip search** says it was bounded. A cap reported as a clean
  result is an instrument that cannot fail.

## What is public and what is not

The tool, the taxonomy in [TAXONOMY.md](TAXONOMY.md) and the seed specimen pack
in `examples/` are public on purpose. A coverage number is only comparable
between two rubrics if the defect classes mean the same thing to both, so the
vocabulary is worth more shared than held.

Domain specimen packs are not published. Ground truth is hand-made, does not
parallelize, and is the part that takes real time to build.

**Nothing derived from paid client work goes into a public pack, ever, without
that client's written permission.**

## Status

Early. The assay and the flip analysis are real and tested; the specimen
material is hand-written, which is the honest bottleneck. Ground truth does not
parallelize.

```
16 passed
```
