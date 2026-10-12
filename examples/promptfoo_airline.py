"""Assay promptfoo's own airline rubric, fairly.

promptfoo runs each test's assertions against THAT test's output only. A pooled
assay (every checkpoint over every specimen) charges test 0's `contains "Seat
updated to 14C"` with false alarms on tests 1 to 3, which correctly lack it.
The first run of this made exactly that mistake and reported 0% coverage with
seven checkpoints as decoration. Most of that was the pooling, not the rubric.

So: one sub-pack per test, one adapted rubric per test, assayed separately.
What remains after that is promptfoo's rubric's own behaviour.

Run:  python examples/promptfoo_airline.py path/to/promptfooconfig.yaml
      (needs pyyaml: pip install 'deadcheck[promptfoo]')
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deadcheck import GENERIC_EVASIONS, Pack, attack, calibrate, earned, power, run
from deadcheck.adapters.promptfoo import from_config
from packs.promptfoo_airline_v1 import BASES, EVASIONS, INJECTIONS

# which clean bases belong to which promptfoo test
_TEST_OF = {"t0_seat_and_bags": 0, "t0_seat_and_bags_reworded": 0,
            "t1_wifi_faq": 1, "t2_third_party_refused": 2,
            "t3_recovered": 3, "t3_recovered_reworded": 3}


def sub_pack(test: int) -> Pack:
    bases = [b for b in BASES if _TEST_OF[b.id] == test]
    ids = {b.id for b in bases}
    injs = [i for i in INJECTIONS if i.applies_to & ids]
    return Pack(f"promptfoo_airline_t{test}", bases, injs,
                f"material implied by promptfoo test {test}")


def main(cfg_path: str) -> int:
    import yaml
    cfg = yaml.safe_load(open(cfg_path))
    print(f"{'test':<5} {'ckpts':>5} {'spec':>5} {'floor':>6} {'cover':>6} "
          f"{'earned':>6} {'FA on reworded':>14} {'evades':>7}")
    for t in (0, 1, 2, 3):
        try:
            pack = sub_pack(t)
        except Exception as exc:                             # noqa: BLE001
            print(f"{t:<5} (sub-pack unbuildable: {exc})")
            continue
        built = pack.build()
        rubric, rep = from_config(cfg, tests=[t], rubric_id=f"promptfoo_t{t}")
        cal = calibrate(built)
        a = run(rubric, built)
        att = attack(rubric, built, GENERIC_EVASIONS + EVASIONS, max_combined=1)
        reworded = [s for s in built.clean if s.id.endswith("_reworded")]
        fa = sum(1 for c in rubric.checkpoints for s in reworded if c.fires(s))
        fa_txt = f"{fa}/{len(rubric.checkpoints) * len(reworded)}" if reworded else "n/a"
        ev = f"{att.evasion_rate:.0%}" if att.n_caught else "n/a"
        er = f"{earned(a, cal):.0%}" if cal.floor < 1 else "n/a"
        print(f"{t:<5} {rep['checkpoints']:>5} {len(built.specimens):>5} "
              f"{cal.floor:>6.0%} {a.coverage:>6.0%} {er:>6} {fa_txt:>14} {ev:>7}")
        for e in att.evaded:
            print(f"      slips: {e.specimen_id} past {', '.join(e.checkpoint_ids)} "
                  f"via {' + '.join(e.evasion_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
