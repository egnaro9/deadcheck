# deadcheck

**Measure what a rubric can and cannot see.** Bring an eval suite; get back three
numbers and the row everyone else leaves out.

Stdlib-only Python, no dependencies, no model in the loop. The same rubric and
the same specimens always produce the same numbers, so a disagreement about a
score is a disagreement about a predicate.

```
python examples/flight_rubric.py
```

## The name

[deadgate](https://github.com/egnaro9/deadgate) finds CI checks that cannot fail:
a required check satisfied by a skipped job, an exit status swallowed by a pipe.
deadcheck is the same question one layer up. A rubric checkpoint that says the
same thing about good and bad work is a check that cannot fail, and it passes
review for the same reason the CI ones do, which is that nobody ever asked it to
prove it could go red.

The report calls those checkpoints **decoration** and tells you to cut them. The
rest of the tool is about what remains.

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
from deadcheck import blocking, what_flips

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

## Building the material

Hand-labelled ground truth is somebody's judgement wearing a lab coat. The
alternative, borrowed from
[reference-fleet](https://github.com/egnaro9/reference-fleet): start from a
clean transcript, apply one documented deterministic injection, and the
resulting specimen carries that defect **by construction**. Its ground truth is
a fact about how it was made, not an opinion about how it reads, and every
generated specimen records which base and which injection produced it.

```python
from deadcheck import Base, Injection, Pack, replace_in_reply

pack = Pack("flight_v1", BASES, [
    Injection("comply_after_declining", "refusal_then_compliance",
              replace_in_reply(DECLINE, DECLINE + " I have booked the change."),
              applies_to=frozenset({"decline_other_traveller"})),
])
specimens = pack.build()       # deterministic, same bytes every time
pack.fingerprint()             # identity of the definition, not the output
```

`packs/flight_v1.py` is the public seed pack: four bases, four injections,
three defect classes, eight specimens.

**The failure this refuses.** An injection that does not change the transcript
produces a specimen labelled defective while being byte-identical to clean
material. Ground truth is then false and **every rubric on earth scores
perfectly against it, forever, with no symptom anywhere.** `Pack.build` raises
rather than warns.

**A property that falls out for free.** Each injection rewrites its own clean
base, so the pack always contains the innocent twin of every defect: the
transcript that *asks* about the seat sits beside the one that *invents* it.
That is what [TAXONOMY.md](TAXONOMY.md) asks of a specimen set, enforced by
construction instead of by discipline.

Generated material agrees with the hand-written set it replaces. Both example
rubrics score identically against each: 33% and 100%, same residual, same
decoration. That agreement is a test, not a claim.

## Calibrating the material

Everything above measures a rubric against a specimen set, which leaves the
obvious question unasked: **is the specimen set any good?** A rubric scoring
100% against weak material means nothing, and that is the same failure as a
checkpoint that fires on everything, one level up.

So run a battery of deliberately naive rubrics over the material and see how far
they get. The sharpest of them is a **deterministic coin flip**: if chance
covers a defect class, that class is not testing anything.

```python
from deadcheck import calibrate, earned

cal = calibrate(specimens)
cal.floor         # best coverage any naive probe reached
cal.difficulty    # 1 - floor
cal.cheap_classes # classes a naive probe already covers
earned(0.85, cal) # a coverage number with the floor subtracted out
```

```
CALIBRATION · flight_v1
  18 specimens (9 clean), 3 defect classes
  floor 0% (best naive probe: coin)
  difficulty 100%
  No naive probe reached any class. Scores against this material are earned.
```

**Calibration found two real defects in this repo's own seed pack**, which is
the best argument for it:

- The first refusal injection appended compliance to a short decline, so the
  defective twin was simply **longer**. A character count separated them and
  `refusal_then_compliance` came back cheap. Clean bases are now written at the
  length of their injected twins.
- With one defective specimen per class, **a coin flip covered two of three
  classes**. Chance either hits the single specimen or does not, and zero false
  alarms across four clean ones is a one-in-sixteen toss. The pack now carries
  three defective specimens per class, and `test_the_public_pack_stays_hard`
  fails if a later edit makes any class reachable again.

And then it found the one that mattered. Against the one-specimen pack the
rewritten rubric scored **100%**. Against the calibrated pack it scored **33%**,
because its checkpoints had been keyword-matched to the exact transcripts
somebody wrote. A coverage number is only as honest as the material underneath
it, and nothing else in this package could have told you that.

## The ratchet

A rubric may not quietly lose the ability to catch something. Snapshot its
measured capability, commit the snapshot, compare every later edit against it.

```python
from deadcheck import capability, compare, load, save

save(capability(run(rubric, specimens), specimens), "capability.json")   # once
report = compare(load("capability.json"), run(rubric, specimens), specimens)
report.ok          # False if anything was lost
print(report.summary())
```

```
RATCHET FAILED · naive_v1 · 2 regressions
  coverage 100% -> 33%
  REGRESSION: lost detection of refusal_then_compliance
  REGRESSION: lost detection of wrong_versus_absent
```

The diff is the easy part. The design problem is that a naive capability gate
is trivial to satisfy dishonestly, so three cases are handled explicitly:

- **Deleting the specimen that catches you.** The baseline fingerprints the
  material, not just the scores. In the test for this, a weakened rubric on
  trimmed material reads **100% coverage before and after, with nothing listed
  as lost**, because the only class it stopped detecting is no longer in the
  material. The removed specimen is the finding.
- **Adding a harder class.** Coverage legitimately falls when the material
  grows. That is not a regression, and the report says so in those words,
  because a gate that punishes new specimens teaches people to stop writing
  them.
- **No baseline.** `load` raises rather than returning an empty comparison.
  A ratchet with nothing to compare against cannot be green.

Separation is compared with a tolerance, so rewording a predicate does not fail
a build over float noise. It is a named argument, not a constant, because
loosening it should be a decision someone makes on purpose.

## The adversary

Of the defects a rubric *does* catch, which can be made to slip?

Not by mutating until the rubric goes quiet, because the cheapest way to
silence a rubric is to delete the defect, and that is a repair rather than an
evasion. An **evasion** here is a transformation declared defect-preserving, so
when the rubric stops firing the defect is still present by construction.

```python
from deadcheck import GENERIC_EVASIONS, attack

rep = attack(rubric, specimens, GENERIC_EVASIONS, max_combined=2)
rep.evasion_rate   # of what it catches, how much slips
rep.held           # nothing slipped
```

**Preservation is declared per class, and has to be.** Swapping two sentences
preserves `confident_staleness` and destroys `refusal_then_compliance`, whose
entire definition is that compliance follows the decline. `unsafe_for` is
checked before an evasion is applied, so the attacker cannot claim a win it did
not earn.

**What it found here.** The rewritten example rubric scored 100% coverage and
was then evaded **44% of the time by doubling the spaces in the reply**. Every
multi-word phrase match broke on one extra space. The predicates now normalise
whitespace, and the generic battery is held off.

**And then the honest part.** Domain paraphrases still defeat it 44% of the
time: `$200` to `200 dollars`, `I cannot` to `I can not`, `I am unable to` to
`I will not be able to`. **That is left unfixed on purpose.** Patching those
exact rewordings is whack-a-mole and is the same overfitting the calibration
already caught once in this repo. A keyword rubric cannot survive paraphrase.
The useful move is to declare the limit, which is what the residual row exists
for, not to add more keywords and call it coverage.

**One number to read carefully.** A blind rubric is trivially unevadable. In
this repo `naive_v1` posts an evasion rate of 0% while never catching six of
nine defects, so the report prints what it never caught beside the rate. An
evasion rate alone would rank a rubric that sees nothing above one that sees
almost everything.

## Can a second person apply it?

Every rubric in this field claims its checkpoints are objective, or "a predicate
a second person could apply." That claim is measurable and almost nobody
measures it. Psychometrics has had the tool since 1960.

A checkpoint has **two** definitions, and they can disagree: the **prose** a
reviewer reads, and the **predicate** the code runs. So agreement is scored
three ways.

```python
from deadcheck import Rating, agree

result = agree(checkpoint, specimens, ratings)
result.verdict   # sound | ambiguous | misimplemented | inconclusive
```

```
AGREEMENT · cp_rot · MISIMPLEMENTED
  2 raters over 6 specimens
  human vs human: raw 100%, kappa +1.00
  ana vs code: raw 0%, kappa -1.00
  ben vs code: raw 0%, kappa -1.00
  THE PROSE AND THE PREDICATE DISAGREE. Raters agree with each other and not
  with the code, so every assay number for this checkpoint describes a rule
  nobody wrote down.
```

**`misimplemented` is the finding nothing else here can make.** Humans applying
the written description agree with each other and disagree with the code. The
assay has been faithfully measuring a rule that exists only in the predicate.
`ambiguous` is the other direction: humans split, so the description is unclear
whatever the code does.

**Kappa's two traps, both handled:**

- It is **undefined**, not zero, when both raters answer the same way on every
  specimen. Expected agreement is already 100% and there is no "beyond chance"
  left to measure. `cohens_kappa` returns `None` with a note rather than
  inventing a number, and the verdict becomes `inconclusive`.
- The **prevalence paradox**: when one answer dominates, a checkpoint with 95%
  raw agreement can post a near-zero kappa. Reporting kappa alone would condemn
  a usable checkpoint, so raw agreement and kappa always print together.

Two more refusals: a single rater agreeing with themselves is not a measurement,
and only specimens **every** rater covered are compared, so a rater who skipped
the hard ones cannot raise the score.

## The certificate

A rating a stranger can check without trusting you. deadcheck emits a
Capability Evidence Bundle in the
[vac-protocol](https://github.com/egnaro9/vac-protocol) v0.2 shape, so the
existing offline verifier reads it. **Still no dependencies:** this writes the
format, it does not import the protocol.

```python
from deadcheck import certify

certify(out_dir, rubric, specimens, assay, calibration, attack)
# writes assay.json, CERTIFICATE.md, vac.json
```

```
rubric-coverage:written_v2 — 3/3 defect classes caught, floor 0%, earned 100%
```

**It refuses to certify against uncalibrated material.** If a naive probe
already reaches a defect class, the coverage number is not interpretable, and
rating it would publish a figure nobody can read. `allow_uncalibrated=True`
issues anyway and makes the floor travel in the claim.

Three properties come from the format and one from this layer:

- **No wall clock.** Every field derives from the inputs or from git, so
  reissuing is byte-identical and a diff means something changed.
- **Closed evidence.** Every sibling of `vac.json` is listed and hashed, so a
  file added afterwards breaks verification instead of riding along.
- **Recomputable headline.** `expect` holds only numbers a verifier derives from
  `assay.json`. Nothing in it is the issuer's word.
- **No dirty stamps.** A certificate issued from a dirty tree is unattributable
  to any commit, which makes `issuer_commit` decoration. It refuses.

The residual is not a footnote here. It is promoted into the claim's
`limitations`, alongside classes nothing declares and classes no specimen
tested, so a reader who checks only the headline still gets handed the gaps.

## The registry

A board that lists whatever it is handed is a directory. A board that can
**refuse** is a rating.

```python
from deadcheck import build, render_markdown

reg = build([cert_dir_a, cert_dir_b, cert_dir_c])
reg.acceptance_rate
```

Nothing is listed until it has been re-verified from the bundle's own bytes:
every number in `expect` recomputed from `assay.json`, every evidence file
re-hashed, the floor checked, and any file present but unlisted treated as a
failure rather than ignored.

```
**2 listed, 1 rejected.**

| rubric       | material            | caught | floor | earned | evades | residual |
|--------------|---------------------|-------:|------:|-------:|-------:|----------|
| naive_v1     | flight_v1 (8ce222ed)|    1/3 |    0% |    33% |     0% | refusal_then_compliance, wrong_versus_absent |
| written_v2   | flight_v1 (8ce222ed)|    3/3 |    0% |   100% |     0% | none on this material |

## Rejected
- tampered — evidence changed since issue: assay.json;
             expect.residual=0 but assay.json recomputes 1
```

**The rejected rows are published with their reasons.** An acceptance rate
without them is not a number, and a board that shows only what passed is making
exactly the omission this tool exists to catch.

Note what caught the tampered bundle: **both checks, independently.** The
evidence hash no longer matched, *and* the headline no longer followed from the
evidence. Either alone would have been a finding; running both means an attacker
has to defeat two unrelated properties.

**Residual is a column, not a footnote,** and the index stores no totals. Counts
are recomputed from the rows on read, so there is no number on the board that
has to be taken on trust.

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
79 passed
```
